"""Cart-session lifecycle: open, ensure-for-table, stale cleanup, and auto-extend."""

import logging
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from typing import cast

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.authentication.models import User
from apps.reservations.models import Reservation, ReservationStatus
from apps.reservations.selectors import get_active_reservation_for_table
from apps.restaurants.models import Table
from apps.restaurants.selectors import get_working_hours_close_at
from common.exceptions import (
    NoActiveReservationError,
    ReservationConflictError,
    ReservationNotFoundError,
    UnservedItemsError,
    WaiterCallCooldownError,
)
from common.hall_events import emit_hall_reservations_updated, emit_hall_session_auto_extended
from common.notification_events import emit_cart_created, emit_kitchen_ticket_injected, emit_waiter_called

from ..models import (
    CartSession,
    CartSessionStatus,
    Order,
    OrderItem,
    OrderPaymentStatus,
    OrderSource,
    Session,
    SessionStatus,
    Ticket,
    TicketStatus,
)
from ..selectors import _resolve_allowed_reservation_participant_ids, get_reservation
from .cart import _broadcast_cart_updated

logger = logging.getLogger(__name__)

_AUTO_EXTEND_AHEAD_MINUTES = 15
_AUTO_EXTEND_DURATION_MINUTES = 30


def create_cart_session(
    *,
    restaurant_id: int,
    reservation_id: str,
    user: User,
) -> CartSession:
    reservation = get_reservation(restaurant_id, reservation_id)
    if reservation is None:
        raise ReservationNotFoundError(f"Reservation {reservation_id} not found.")

    allowed_participants = _resolve_allowed_reservation_participant_ids(reservation)
    if not allowed_participants or user.id not in allowed_participants:
        raise PermissionDenied("Only reservation participants may open a cart session.")

    with transaction.atomic():
        existing = (
            CartSession.objects.select_for_update()
            .filter(reservation=reservation, status=CartSessionStatus.ACTIVE)
            .first()
        )
        if existing is not None:
            existing.participants.add(*allowed_participants)
            return existing

        created = False
        try:
            with transaction.atomic():
                session = CartSession.objects.create(
                    restaurant_id=restaurant_id,
                    reservation=reservation,
                    created_by=user,
                )
                created = True
        except IntegrityError:
            session = CartSession.objects.get(reservation=reservation, status=CartSessionStatus.ACTIVE)

        if created:
            table_number = reservation.table.public_number if reservation.table else ""
            transaction.on_commit(
                lambda: emit_cart_created(
                    restaurant_id,
                    session_id=str(session.public_id),
                    table_number=table_number,
                    guest_name=user.get_full_name() if user else None,
                )
            )

        session.participants.add(*allowed_participants)
    return session


def ensure_active_cart_for_table(
    *,
    table: Table,
    user: User | None = None,
) -> CartSession:
    """Return (or create) the active cart session for the table's active reservation.

    Finds the reservation in progress on the table. Raises NoActiveReservationError
    if there is none. Safe under concurrent scans: relies on the
    one_active_per_reservation unique constraint so two callers can never create
    two active sessions for the same reservation.

    NOTE: unlike create_cart_session, this intentionally does NOT gate on
    reservation participants. It backs the public QR/GuestInit (AllowAny) flow,
    where the issued guest token is already scoped to one cart_session_id. Any
    future *authenticated* caller would bypass participant gating here — add an
    explicit participant check before reusing this from an authenticated path.
    """
    reservation = get_active_reservation_for_table(table)
    if reservation is None:
        raise NoActiveReservationError(f"Table {table.public_id} has no active reservation.")

    with transaction.atomic():
        existing = (
            CartSession.objects.select_for_update()
            .filter(reservation=reservation, status=CartSessionStatus.ACTIVE)
            .first()
        )
        if existing is not None:
            if user is not None:
                existing.participants.add(user)
            return existing

        created = False
        try:
            with transaction.atomic():
                session = CartSession.objects.create(
                    restaurant_id=reservation.restaurant_id,
                    reservation=reservation,
                    created_by=user,
                )
                created = True
        except IntegrityError:
            session = CartSession.objects.get(reservation=reservation, status=CartSessionStatus.ACTIVE)

        if created:
            transaction.on_commit(
                lambda: emit_cart_created(
                    reservation.restaurant_id,
                    session_id=str(session.public_id),
                    table_number=table.public_number,
                    guest_name=user.get_full_name() if user else None,
                )
            )

        if user is not None:
            session.participants.add(user)
    return session


# Keep in sync with WAITER_CALL_SENT_RESET_MS in
# table-mate-frontend/src/features/menu/pages/MenuPage/MenuPage.tsx — the
# guest's button should re-enable right as this cooldown expires.
_WAITER_CALL_COOLDOWN_SECONDS = 60


def call_waiter(*, session: CartSession, guest_name: str | None = None) -> None:
    """Notify staff that the guests at this table want a waiter.

    Rate-limited per cart session so a guest tapping the button repeatedly
    doesn't flood the staff notification stream.
    """
    cooldown_key = f"waiter_call_cooldown:{session.public_id}"
    try:
        acquired = cache.add(cooldown_key, "1", timeout=_WAITER_CALL_COOLDOWN_SECONDS)
    except Exception:
        # Mirrors _broadcast_staff_event's tolerance for a flaky cache/Redis:
        # don't fail the guest's request over a rate-limit check, just skip
        # rate-limiting for this call.
        logger.exception("Waiter-call cooldown check failed for session %s", session.public_id)
        acquired = True
    if not acquired:
        raise WaiterCallCooldownError

    table = session.reservation.table
    table_number = table.public_number if table else ""
    emit_waiter_called(
        session.restaurant_id,
        session_id=str(session.public_id),
        table_number=table_number,
        guest_name=guest_name,
    )


_STALE_CART_BATCH_SIZE = 500
_OVERDUE_VISIT_BATCH_SIZE = 200
_PREORDER_INJECT_BATCH_SIZE = 200


def close_stale_cart_sessions(*, restaurant_id: int | None = None, batch_size: int = _STALE_CART_BATCH_SIZE) -> int:
    """Close active carts whose reservation is finished or past its end time.

    Keeps dead active CartSessions from piling up after a visit ends. Returns
    the number of carts closed. Time-valid active reservations are left alone.

    Closes in bounded batches instead of one global UPDATE, so a large backlog
    doesn't take a wide lock in a single statement. ``skip_locked`` lets it step
    over rows another transaction is already touching. Pass ``restaurant_id`` to
    scope a run to one tenant.
    """
    now = timezone.now()
    base = (
        CartSession.objects.filter(status=CartSessionStatus.ACTIVE)
        .filter(
            Q(reservation__status__in=[ReservationStatus.COMPLETED, ReservationStatus.CANCELLED])
            | Q(reservation__session__ends_at__lt=now)
            | (
                Q(reservation__end_at__lt=now)
                & ~Exists(Session.objects.filter(reservation=OuterRef("reservation")))
            )
        )
    )
    if restaurant_id is not None:
        base = base.filter(restaurant_id=restaurant_id)

    total_closed = 0
    while True:
        with transaction.atomic():
            batch_ids = list(base.values_list("pk", flat=True)[:batch_size])
            if not batch_ids:
                break
            batch = list(
                CartSession.objects.filter(pk__in=batch_ids).select_for_update(skip_locked=True)
            )
            if not batch:
                break

            # Re-validate staleness under the lock — a concurrent auto-extend
            # may have pushed reservation__session__ends_at past now since the
            # first SELECT.  Re-run the staleness filter (without FOR UPDATE,
            # so outer joins in the filter are legal) to exclude rows that are
            # no longer stale.
            still_stale_ids = set(
                base.filter(pk__in=[c.pk for c in batch]).values_list("pk", flat=True)
            )
            batch = [c for c in batch if c.pk in still_stale_ids]
            if not batch:
                if len(batch_ids) < batch_size:
                    break
                continue

            for cart in batch:
                cart.status = CartSessionStatus.CLOSED
            CartSession.objects.bulk_update(batch, ["status"])

        # Tell any open guest drawer its cart has closed, so it stops accepting taps.
        for cart in batch:
            _broadcast_cart_updated(cart)
        total_closed += len(batch)
        if len(batch) < batch_size:
            break
    return total_closed


def _find_conflict_limit(
    session: Session,
    target_end: datetime,
) -> datetime | None:
    """Return the earliest conflicting reservation's effective start, or None."""
    from apps.reservations.services import _check_reservation_conflict

    try:
        _check_reservation_conflict(
            restaurant_id=session.restaurant_id,
            table=session.table,
            start_at=session.opened_at,
            end_at=target_end,
            current_reservation_id=session.reservation_id,
        )
    except ReservationConflictError:
        pass
    else:
        return None

    # Conflict found — find the earliest one using the same overlap predicate
    # as _check_reservation_conflict so the clamp always matches the detection.
    open_session_sq = (
        Session.objects.filter(
            reservation=OuterRef("pk"),
            status=SessionStatus.OPEN,
        )
        .order_by("opened_at")
    )

    earliest = (
        Reservation.objects.filter(
            restaurant_id=session.restaurant_id,
            table=session.table,
            status__in=[ReservationStatus.PENDING, ReservationStatus.ACTIVE],
        )
        .exclude(id=session.reservation_id)
        .annotate(
            eff_start=Coalesce(
                Subquery(open_session_sq.values("opened_at")[:1]),
                "start_at",
            ),
            eff_end=Coalesce(
                Subquery(open_session_sq.values("ends_at")[:1]),
                "end_at",
            ),
        )
        .filter(
            eff_start__lt=target_end,
            eff_end__gt=session.opened_at,
        )
        .order_by("eff_start")
        .first()
    )
    if earliest is not None:
        return cast(datetime | None, earliest.eff_start)
    return None


def auto_extend_session(session: Session) -> dict[str, object]:
    """Attempt to extend an open session by up to 30 minutes.

    Respects working-hours boundaries (clamps to closing time) and upcoming
    reservation conflicts (clamps to the conflict's start). Returns a dict
    with ``extended`` (bool), ``clamped_by`` (str or None), and
    ``new_ends_at`` (datetime or None).

    Safe under concurrency: acquires a row-level lock on both the session and
    its table so the conflict-check-then-write is serialized against all other
    occupancy writers (create_reservation, _prolong_active_reservation,
    batch_update_reservations, activate_pending_reservation).
    """
    with transaction.atomic():
        # Re-fetch under lock so we serialize against _prolong_active_reservation
        # and any other session mutator, and re-read ends_at fresh.
        locked = (
            Session.objects.select_for_update()
            .filter(pk=session.pk, status=SessionStatus.OPEN)
            .first()
        )
        if locked is None:
            return {"extended": False, "clamped_by": None, "new_ends_at": None}

        # The free auto-extend fires once per session. After that the table
        # is genuinely overdue and it's up to staff to prolong or close it.
        if locked.auto_extended:
            return {"extended": False, "clamped_by": None, "new_ends_at": None}

        # Serialize against create_reservation, batch_update, activate_pending
        # which all lock the Table row before writing occupancy.
        Table.objects.select_for_update().get(pk=locked.table_id)

        now = timezone.now()

        if locked.ends_at is None or locked.ends_at > now + timedelta(minutes=_AUTO_EXTEND_AHEAD_MINUTES):
            return {"extended": False, "clamped_by": None, "new_ends_at": None}

        target = now + timedelta(minutes=_AUTO_EXTEND_DURATION_MINUTES)
        reason: str | None = None

        # 1. Clamp to working hours
        close_at = get_working_hours_close_at(locked.restaurant_id, now)
        if close_at is not None and target > close_at:
            target = close_at
            reason = "working_hours"

        # 2. Clamp to upcoming conflict
        conflict_limit = _find_conflict_limit(locked, target)
        if conflict_limit is not None and conflict_limit < target:
            target = conflict_limit
            reason = "conflict"

        # 3. No meaningful extension
        if target <= locked.ends_at:
            return {"extended": False, "clamped_by": reason, "new_ends_at": None}

        # 4. Apply
        locked.ends_at = target
        locked.auto_extended = True
        locked.save(update_fields=["ends_at", "auto_extended", "updated_at"])

        restaurant_id = locked.restaurant_id
        table_id = str(locked.table.public_id)
        target_iso = target.isoformat()

        transaction.on_commit(
            lambda: emit_hall_reservations_updated(restaurant_id, table_ids=[table_id])
        )

        if reason == "conflict":
            transaction.on_commit(
                lambda: emit_hall_session_auto_extended(
                    restaurant_id,
                    table_id=table_id,
                    ends_at=target_iso,
                    clamped_by="conflict",
                )
            )

        logger.info(
            "Auto-extended session %s (table %s) to %s (reason=%s)",
            locked.public_id,
            table_id,
            target_iso,
            reason or "none",
        )

        return {"extended": True, "clamped_by": reason, "new_ends_at": target}


def auto_extend_all_sessions(restaurant_id: int | None = None) -> list[dict[str, object]]:
    """Auto-extend all open sessions nearing their end time.

    Scopes to ``restaurant_id`` when provided. Returns a list of per-session
    result dicts.
    """
    now = timezone.now()
    threshold = now + timedelta(minutes=_AUTO_EXTEND_AHEAD_MINUTES)

    qs = Session.objects.filter(
        status=SessionStatus.OPEN,
        ends_at__isnull=False,
        ends_at__lte=threshold,
    ).select_related("table", "reservation")
    if restaurant_id is not None:
        qs = qs.filter(restaurant_id=restaurant_id)

    results: list[dict[str, object]] = []
    for session in qs:
        result = auto_extend_session(session)
        results.append(result)

    return results


def close_overdue_visit_sessions(*, batch_size: int = _OVERDUE_VISIT_BATCH_SIZE) -> int:
    """Close OPEN sessions whose active reservation ended beyond the grace window."""
    from apps.orders.billing import close_visit_session

    now = timezone.now()
    grace_minutes = max(int(getattr(settings, "SESSION_OVERDUE_AUTO_CLOSE_MINUTES", 20)), 0)
    cutoff = now - timedelta(minutes=grace_minutes)
    base = Session.objects.filter(
        status=SessionStatus.OPEN,
        reservation__status=ReservationStatus.ACTIVE,
        ends_at__lte=cutoff,
    )

    total_closed = 0
    last_pk = 0
    while True:
        batch_ids = list(
            base.filter(pk__gt=last_pk).order_by("pk").values_list("pk", flat=True)[:batch_size]
        )
        if not batch_ids:
            break

        last_pk = batch_ids[-1]

        with transaction.atomic():
            sessions = list(
                Session.objects.select_for_update(skip_locked=True)
                .filter(pk__in=batch_ids, status=SessionStatus.OPEN, reservation__status=ReservationStatus.ACTIVE)
                .order_by("pk")
            )

            for session in sessions:
                # Re-check under lock so a concurrent auto-extend can move the
                # session out of the overdue bucket between the initial SELECT
                # and the eventual close.
                if session.ends_at is None or session.ends_at > cutoff:
                    continue
                try:
                    close_visit_session(session=session, actor=None)
                except UnservedItemsError:
                    # One bad session must not wedge the cleanup run; the row
                    # remains overdue and will be retried on a later pass (and,
                    # once far enough past shift end, force-closed regardless —
                    # see force_close_sessions_past_shift_end).
                    continue
                total_closed += 1

    return total_closed


def force_close_sessions_past_shift_end(
    *, now: datetime | None = None, batch_size: int = _OVERDUE_VISIT_BATCH_SIZE
) -> int:
    """Force-close OPEN sessions left over an hour past their restaurant's shift end.

    close_overdue_visit_sessions refuses to close a session that still has
    unserved items, so a session can stay wedged open forever if staff never
    mark those items served/voided — blocking the table for every reservation
    after it. Once a restaurant is this far past closing, freeing the table
    matters more than that guard, so this force-closes regardless.
    """
    from apps.orders.billing import close_visit_session

    now = now or timezone.now()
    grace_minutes = max(int(getattr(settings, "SHIFT_END_FORCE_CLOSE_GRACE_MINUTES", 60)), 0)
    grace = timedelta(minutes=grace_minutes)

    restaurant_ids = list(
        Session.objects.filter(status=SessionStatus.OPEN, reservation__status=ReservationStatus.ACTIVE)
        .values_list("restaurant_id", flat=True)
        .distinct()
    )

    total_closed = 0
    for restaurant_id in restaurant_ids:
        # No configured working hours → no shift boundary to force-close against.
        close_at = get_working_hours_close_at(restaurant_id, now)
        if close_at is None or now < close_at + grace:
            continue

        base = Session.objects.filter(
            status=SessionStatus.OPEN,
            reservation__status=ReservationStatus.ACTIVE,
            restaurant_id=restaurant_id,
        )

        last_pk = 0
        while True:
            batch_ids = list(
                base.filter(pk__gt=last_pk).order_by("pk").values_list("pk", flat=True)[:batch_size]
            )
            if not batch_ids:
                break

            last_pk = batch_ids[-1]

            with transaction.atomic():
                sessions = list(
                    Session.objects.select_for_update(skip_locked=True)
                    .filter(pk__in=batch_ids, status=SessionStatus.OPEN, reservation__status=ReservationStatus.ACTIVE)
                    .order_by("pk")
                )
                for session in sessions:
                    close_visit_session(session=session, actor=None, force=True)
                    total_closed += 1

    return total_closed


def _preorder_orders_awaiting_kitchen() -> QuerySet[Order]:
    """Paid pre-order rounds the kitchen hasn't been handed yet."""
    return Order.objects.filter(
        payment_status=OrderPaymentStatus.PAID,
        source=OrderSource.CUSTOMER_PREORDER,
        tickets__isnull=True,
    )


def _inject_preorder_orders(
    order_ids: Iterable[int],
    *,
    now: datetime,
    revalidate: Callable[[Order], bool] | None = None,
) -> int:
    """Ticket each of these pre-order Orders and tell the kitchen.

    This is the last step checkout_cart_session does immediately for a live
    order: create the Ticket, attach it to the order's items, notify the
    kitchen. Every condition is re-checked under the row lock, since a
    concurrent injection or a cancellation may have landed since the ids were
    selected; ``revalidate`` adds the caller's own conditions to that re-check.
    """
    injected = 0
    for order_id in order_ids:
        with transaction.atomic():
            order = (
                Order.objects.select_for_update(skip_locked=True)
                .select_related("session__table", "session__reservation", "restaurant")
                .filter(pk=order_id)
                .first()
            )
            if order is None:
                # skip_locked: the row is either gone or held by another
                # transaction. Benign on the periodic sweep, which comes back
                # in a minute — but at seating time this is the whole reason
                # inject_scheduled_preorders has to cover ACTIVE bookings too,
                # so say it happened rather than dropping the round in silence.
                logger.info("Pre-order order id=%s was busy or gone; not ticketed.", order_id)
                continue
            if order.payment_status != OrderPaymentStatus.PAID:
                continue
            if order.source != OrderSource.CUSTOMER_PREORDER:
                continue
            if Ticket.objects.filter(order=order).exists():
                continue
            session = order.session
            if session.reservation is None:
                continue
            if revalidate is not None and not revalidate(order):
                continue

            ticket = Ticket.objects.create(
                restaurant=order.restaurant,
                session=session,
                order=order,
                status=TicketStatus.INCOMING,
                injected_at=now,
            )
            items_count = OrderItem.objects.filter(order=order).update(ticket=ticket)
            logger.info(
                "Handed pre-order %s to the kitchen as ticket %s (%s items).",
                order.public_id,
                ticket.public_id,
                items_count,
            )

        def _emit_ticket_injected(
            tk: Ticket = ticket, sess: Session = session, cnt: int = items_count
        ) -> None:
            emit_kitchen_ticket_injected(
                sess.restaurant_id,
                ticket_id=str(tk.public_id),
                table_number=sess.table.public_number,
                items_count=cnt,
            )

        transaction.on_commit(_emit_ticket_injected)
        injected += 1

    return injected


def inject_preorders_for_reservation(reservation: Reservation) -> int:
    """Hand the kitchen any pre-order rounds still waiting, because the party just sat down.

    inject_scheduled_preorders only sweeps PENDING reservations due within
    PREORDER_LEAD_MINUTES, and seating has no early window — a party seated
    more than that ahead of its booking flips to ACTIVE before the sweep ever
    matches, and the food would never be cooked. Seating is the other moment
    the kitchen needs the ticket, so ask for it here as well; rounds the sweep
    already injected are skipped on their existing Ticket.
    """
    order_ids = list(
        _preorder_orders_awaiting_kitchen()
        .filter(session__reservation=reservation)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    if not order_ids:
        return 0
    return _inject_preorder_orders(order_ids, now=timezone.now())


def inject_scheduled_preorders(*, batch_size: int = _PREORDER_INJECT_BATCH_SIZE) -> int:
    """Create the kitchen Ticket for paid pre-orders nearing their reservation's start_at.

    confirm_and_pay_preorder builds and pays an Order/OrderItems up front but
    leaves them ticket-less, so the kitchen doesn't see them yet. This finds
    paid, ticket-less orders due within PREORDER_LEAD_MINUTES. A booking
    seated before this runs is normally handled by
    inject_preorders_for_reservation instead.

    ACTIVE bookings are swept as well as PENDING ones, as a backstop for
    inject_preorders_for_reservation. That one selects with skip_locked, so a
    round whose Order row happens to be locked at seating time (an in-flight
    cancel_preorder, say) is silently passed over — and once the booking is
    ACTIVE, a PENDING-only sweep never came back for it. The guest had paid,
    the kitchen never saw the food, and nothing said so.

    The lead window applies only to PENDING rounds. Once the party is seated
    there is nothing left to wait for, and a booking seated ahead of its slot
    still has a start_at too far out to match the window.
    """
    now = timezone.now()
    lead_minutes = max(int(getattr(settings, "PREORDER_LEAD_MINUTES", 20)), 0)
    cutoff = now + timedelta(minutes=lead_minutes)

    base = _preorder_orders_awaiting_kitchen().filter(
        Q(
            session__reservation__status=ReservationStatus.PENDING,
            session__reservation__start_at__lte=cutoff,
        )
        | Q(session__reservation__status=ReservationStatus.ACTIVE)
    )

    def _still_due(order: Order) -> bool:
        reservation = order.session.reservation
        if reservation is None:
            return False
        if reservation.status == ReservationStatus.ACTIVE:
            logger.warning(
                "Recovering pre-order %s: its booking was seated before the order was ticketed.",
                order.public_id,
            )
            return True
        return reservation.status == ReservationStatus.PENDING and reservation.start_at <= cutoff

    total_injected = 0
    last_pk = 0
    while True:
        batch_ids = list(base.filter(pk__gt=last_pk).order_by("pk").values_list("pk", flat=True)[:batch_size])
        if not batch_ids:
            break
        last_pk = batch_ids[-1]
        total_injected += _inject_preorder_orders(batch_ids, now=now, revalidate=_still_due)

    # Only when something moved: this runs every 60s, and a "nothing to do"
    # line each time would bury the ones that matter.
    if total_injected:
        logger.info("Handed %s pre-order round(s) to the kitchen.", total_injected)
    return total_injected
