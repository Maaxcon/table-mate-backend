import logging
from datetime import date, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.authentication.models import RoleCode, User
from apps.orders.billing import close_reservation_carts, close_visit_session, ensure_visit_session
from apps.orders.models import OrderItem, OrderItemStatus, Session, SessionStatus
from apps.orders.services.sessions import inject_preorders_for_reservation
from apps.restaurants.models import RestaurantSettings, Table
from apps.restaurants.selectors import _DAY_KEYS, _hhmm_to_minutes
from common.exceptions import ReservationCancelError, ReservationConflictError, RestaurantClosedError
from common.hall_events import (
    emit_hall_new_reservation,
    emit_hall_reservation_cancelled,
    emit_hall_reservations_updated,
    emit_hall_table_status_changed,
)
from common.notification_events import emit_hall_new_reservation_notification

from ..editor.selectors import get_available_tables
from .models import Reservation, ReservationStatus, ReservationType

logger = logging.getLogger(__name__)


def check_availability(
    restaurant_id: int,
    table_id: str,
    start_at: datetime,
    end_at: datetime,
    current_reservation_id: int | None = None,
) -> bool:
    available = get_available_tables(
        restaurant_id=restaurant_id,
        start_at=start_at,
        end_at=end_at,
        current_reservation_id=current_reservation_id,
    )
    return available.filter(public_id=table_id).exists()


def _check_reservation_conflict(
    *,
    restaurant_id: int,
    table: Table,
    start_at: datetime,
    end_at: datetime,
    current_reservation_id: int | None = None,
) -> None:
    # For an ACTIVE reservation the occupied window is the OPEN session's actuals
    # [opened_at, ends_at]; for PENDING it's the booked [start_at, end_at]. Coalesce
    # falls back to the booked values when there is no open session (pending). The
    # fallback also covers any legacy session predating the ends_at backfill
    # (migration 0025) — a safety net, not the primary mechanism.
    open_session = (
        Session.objects.filter(
            reservation=OuterRef("pk"),
            status=SessionStatus.OPEN,
        )
        .order_by("opened_at")
    )

    qs = (
        Reservation.objects.filter(
            restaurant_id=restaurant_id,
            table=table,
            status__in=[ReservationStatus.PENDING, ReservationStatus.ACTIVE],
        )
        .annotate(
            eff_start=Coalesce(Subquery(open_session.values("opened_at")[:1]), "start_at"),
            eff_end=Coalesce(Subquery(open_session.values("ends_at")[:1]), "end_at"),
        )
        .filter(
            eff_start__lt=end_at,
            eff_end__gt=start_at,
        )
    )
    if current_reservation_id is not None:
        qs = qs.exclude(id=current_reservation_id)
    conflict = qs.first()
    if conflict is not None:
        raise ReservationConflictError(
            "Table is not available during the requested time.",
            conflicting_reservation_id=str(conflict.public_id),
        )

    # A new/edited reservation may not begin before a party already seated on this
    # table: pending bookings queue AFTER the active session, never before it. The
    # anchor is the session's opened_at (when the party actually sat down).
    seated = Session.objects.filter(
        restaurant_id=restaurant_id,
        table=table,
        status=SessionStatus.OPEN,
        opened_at__gt=start_at,
    )
    if current_reservation_id is not None:
        seated = seated.exclude(reservation_id=current_reservation_id)
    seated_session = seated.select_related("reservation").first()
    if seated_session is not None:
        raise ReservationConflictError(
            "Table is occupied; a new reservation must start after the seated party.",
            conflicting_reservation_id=str(seated_session.reservation.public_id),
        )

@transaction.atomic
def create_reservation(
    *,
    restaurant_id: int,
    customer_id: int,
    table_id: str,
    guest_count: int,
    start_at: datetime,
    end_at: datetime,
    notes: str | None = None,
    actor: User | None = None,
) -> Reservation:
    table = (
        Table.objects.filter(restaurant_id=restaurant_id, public_id=table_id, active=True).select_for_update().first()
    )

    if not table:
        raise NotFound("Table not found or inactive.")

    _check_reservation_conflict(
        restaurant_id=restaurant_id,
        table=table,
        start_at=start_at,
        end_at=end_at,
    )

    settings = RestaurantSettings.objects.filter(restaurant_id=restaurant_id).first()
    if settings and settings.working_hours:
        tz = ZoneInfo(settings.timezone) if settings.timezone else ZoneInfo("UTC")
        local_start = start_at.astimezone(tz)
        day_key = _DAY_KEYS[local_start.weekday()]
        day_hours = settings.working_hours.get(day_key)
        if not day_hours:
            raise RestaurantClosedError(f"Restaurant closed on {day_key}.")
        open_min = _hhmm_to_minutes(day_hours.get("open"))
        close_min = _hhmm_to_minutes(day_hours.get("close"))
        if open_min is not None and close_min is not None:
            start_min = local_start.hour * 60 + local_start.minute
            local_end = end_at.astimezone(tz)
            end_min = local_end.hour * 60 + local_end.minute
            if close_min > open_min:
                if start_min < open_min or end_min > close_min:
                    raise RestaurantClosedError("Reservation falls outside operating hours.")
            else:
                if not (start_min >= open_min or start_min < close_min) or not (
                    end_min >= open_min or end_min < close_min
                ):
                    raise RestaurantClosedError("Reservation falls outside operating hours.")

    reservation = Reservation.objects.create(
        restaurant_id=restaurant_id,
        customer_id=customer_id,
        table=table,
        guest_count=guest_count,
        start_at=start_at,
        end_at=end_at,
        status=ReservationStatus.PENDING,
        notes=notes or "",
    )

    if actor is not None:
        transaction.on_commit(
            lambda: emit_hall_new_reservation(
                restaurant_id,
                reservation_id=str(reservation.public_id),
                table_id=str(table.public_id),
                start_at=start_at.isoformat(),
                end_at=end_at.isoformat(),
                actor=actor,
            )
        )

    transaction.on_commit(
        lambda: emit_hall_new_reservation_notification(
            restaurant_id,
            reservation_id=str(reservation.public_id),
            table_number=table.public_number,
            guest_name=actor.get_full_name() if actor else None,
            guest_count=guest_count,
        )
    )

    return reservation


@transaction.atomic
def create_staff_reservation(
    *,
    restaurant_id: int,
    table_id: str,
    guest_count: int,
    start_at: datetime,
    end_at: datetime,
    guest_name: str,
    guest_phone: str = "",
    notes: str | None = None,
    actor: User,
) -> Reservation:
    table = (
        Table.objects.filter(restaurant_id=restaurant_id, public_id=table_id, active=True).select_for_update().first()
    )

    if not table:
        raise NotFound("Table not found or inactive.")

    _check_reservation_conflict(
        restaurant_id=restaurant_id,
        table=table,
        start_at=start_at,
        end_at=end_at,
    )

    staff_notes = notes or ""
    if guest_phone:
        staff_notes = f"Phone: {guest_phone}" + (f"\n{staff_notes}" if staff_notes else "")

    reservation = Reservation.objects.create(
        restaurant_id=restaurant_id,
        customer=None,
        guest_name=guest_name,
        table=table,
        guest_count=guest_count,
        start_at=start_at,
        end_at=end_at,
        type=ReservationType.PRE_BOOKED,
        status=ReservationStatus.PENDING,
        created_by_staff=True,
        notes=staff_notes or None,
    )

    transaction.on_commit(
        lambda: emit_hall_new_reservation(
            restaurant_id,
            reservation_id=str(reservation.public_id),
            table_id=str(table.public_id),
            start_at=start_at.isoformat(),
            end_at=end_at.isoformat(),
            actor=actor,
        )
    )

    transaction.on_commit(
        lambda: emit_hall_new_reservation_notification(
            restaurant_id,
            reservation_id=str(reservation.public_id),
            table_number=table.public_number,
            guest_name=guest_name,
            guest_count=guest_count,
        )
    )

    return reservation


@transaction.atomic
def cancel_reservation(reservation: Reservation, *, actor: User | None = None) -> Reservation:
    """Cancel a pending or active reservation. Rejects any other state.

    Mirrors reschedule/activate: the state-machine lives here, not in the view.
    Staff can cancel an ACTIVE (seated) reservation directly — unlike the
    normal checkout flow (close_session), this doesn't require order items to
    be served/voided first, since the booking is being voided outright. Any
    lingering OPEN session must still be closed here — not because it would
    otherwise leave the table looking occupied (get_session_grace_cutoffs
    already filters reservation__status=ACTIVE, so a cancelled reservation's
    session never blocks availability), but because a dangling open session
    would trip activate_pending_reservation's "table already has an active
    session" guard the next time this table's queue is worked.

    Also closes any still-ACTIVE CartSession, mirroring close_visit_session's
    fuller teardown — checkout_cart_session only checks the cart's own
    status, not the reservation's, so leaving a cart open after cancelling a
    seated booking would let the guest keep ordering/checking out (injecting
    a kitchen ticket) against a reservation staff already ended.

    Emits the same real-time hall events close_session does, so the floor
    stays live instead of stale until a reload: HALL_TABLE_STATUS_CHANGED
    (occupied->free) when a session was actually closed, and
    HALL_RESERVATION_CANCELLED whenever the reservation had a table —
    including the PENDING case with no session, so the customer floor drops
    it from "upcoming" and refreshes slot availability. actor is optional
    (as with create_reservation) — omitting it just skips the events.
    """
    locked = Reservation.objects.select_for_update().get(pk=reservation.pk)
    if locked.status not in {ReservationStatus.PENDING, ReservationStatus.ACTIVE}:
        raise ReservationCancelError("Only pending or active reservations can be cancelled.")
    locked.status = ReservationStatus.CANCELLED
    locked.save(update_fields=["status", "updated_at"])

    session = Session.objects.filter(
        reservation=locked,
        status__in=[SessionStatus.OPEN, SessionStatus.SCHEDULED],
    ).first()
    # A SCHEDULED session (paid pre-order, party never seated) has to be closed
    # too, or cancelling leaves it dangling forever. It never occupied the
    # table, though, so only a previously-OPEN one may report occupied->free.
    was_open = session is not None and session.status == SessionStatus.OPEN
    if session:
        session.status = SessionStatus.CLOSED
        session.save(update_fields=["status", "updated_at"])

    close_reservation_carts(locked)

    table = locked.table
    if actor is not None and table is not None:
        if session is not None and was_open:
            transaction.on_commit(
                lambda: emit_hall_table_status_changed(
                    locked.restaurant_id,
                    table_id=str(table.public_id),
                    previous_status="occupied",
                    current_status="free",
                    session_id=str(session.public_id),
                    actor=actor,
                )
            )
        transaction.on_commit(
            lambda: emit_hall_reservation_cancelled(
                locked.restaurant_id,
                reservation_id=str(locked.public_id),
                table_id=str(table.public_id),
                actor=actor,
            )
        )
        transaction.on_commit(
            lambda: emit_hall_reservations_updated(locked.restaurant_id, table_ids=[str(table.public_id)])
        )

    return locked


_NO_SHOW_BATCH_SIZE = 200


def _close_out_cooked_noshow(reservation: Reservation) -> None:
    """End a no-show whose pre-order the kitchen had already cooked.

    The food was made and paid for, so there is nothing to refund — the
    booking is spent, not cancelled. It still has to reach a terminal status:
    left PENDING, activate_pending_reservation's "earlier pending reservation"
    guard blocks every later booking on that table for good, and the cooked
    ticket sits on the kitchen board forever because no cleanup job looks at a
    SCHEDULED session.

    Completing (rather than cancelling) keeps the charge and lets
    close_visit_session snapshot a receipt, so the guest can see what they
    paid for. force=True voids whatever the kitchen never served and bumps its
    tickets off the board.
    """
    from apps.orders.billing import close_visit_session

    reservation.status = ReservationStatus.COMPLETED
    reservation.save(update_fields=["status", "updated_at"])

    session = (
        Session.objects.filter(reservation=reservation).exclude(status=SessionStatus.CLOSED).first()
    )
    if session is None:
        close_reservation_carts(reservation)
        return
    close_visit_session(session=session, actor=None, force=True)


def expire_noshow_reservations(*, batch_size: int = _NO_SHOW_BATCH_SIZE) -> int:
    """Auto-cancel PENDING reservations nobody seated within grace of start_at.

    Example: booked for 12:00, grace is 2 hours — if nobody has seated the
    table (staff clicking "seat", or the guest self-seating) by 14:00, the
    booking closes. Without this, a forgotten pending booking sits PENDING
    forever — and activate_pending_reservation's "earlier pending reservation"
    guard then permanently blocks every later booking on that table, since the
    guard has no staleness cutoff of its own.

    A paid pre-order is cancelled too (refunded — payment here is simulated)
    unless the kitchen already has a Ticket for it: that food was cooked and
    isn't refundable, so that booking is completed rather than cancelled (see
    _close_out_cooked_noshow). Either way it leaves PENDING, which is the
    point — a booking stuck PENDING blocks its table for good.
    """
    from apps.orders.billing import cancel_preorder_rounds
    from apps.orders.models import Order, OrderPaymentStatus, OrderSource
    from common.exceptions import PreorderNotAllowedError

    now = timezone.now()
    grace_minutes = max(int(getattr(settings, "RESERVATION_NO_SHOW_GRACE_MINUTES", 120)), 0)
    cutoff = now - timedelta(minutes=grace_minutes)

    base = Reservation.objects.filter(status=ReservationStatus.PENDING, start_at__lte=cutoff)

    total_expired = 0
    last_pk = 0
    while True:
        batch_ids = list(base.filter(pk__gt=last_pk).order_by("pk").values_list("pk", flat=True)[:batch_size])
        if not batch_ids:
            break
        last_pk = batch_ids[-1]

        with transaction.atomic():
            # Locking + re-filtering here (not a separate earlier read) closes a
            # race with activate_pending_reservation: without holding this lock
            # across the whole decision, a guest seated between our batch SELECT
            # and the eventual cancel_reservation call would still get cancelled
            # out from under them — cancel_reservation itself permits ACTIVE too
            # (it's also used for staff cancelling a seated party), so it can't
            # catch that case on its own.
            reservations = list(
                Reservation.objects.select_for_update(skip_locked=True)
                .filter(pk__in=batch_ids, status=ReservationStatus.PENDING, start_at__lte=cutoff)
                .order_by("pk")
            )
            for reservation in reservations:
                paid_orders = list(
                    Order.objects.filter(
                        session__reservation=reservation,
                        source=OrderSource.CUSTOMER_PREORDER,
                        payment_status=OrderPaymentStatus.PAID,
                    ).order_by("pk")
                )
                try:
                    cancel_preorder_rounds(orders=paid_orders, user=None)
                except PreorderNotAllowedError:
                    # Real food was already cooked on at least one round, so
                    # none of it is refundable — close the booking out instead
                    # of cancelling it.
                    logger.info(
                        "No-show %s had a cooked pre-order; completing instead of cancelling.",
                        reservation.public_id,
                    )
                    _close_out_cooked_noshow(reservation)
                    total_expired += 1
                    continue

                try:
                    cancel_reservation(reservation, actor=None)
                except ReservationCancelError:
                    continue
                total_expired += 1

    return total_expired


def _prolong_active_reservation(
    reservation: Reservation,
    validated_data: dict[str, Any],
) -> Reservation:
    """Prolong/annotate a seated party without touching the booked reservation.

    For an ACTIVE reservation the booking (table/start_at/end_at) is immutable; the
    actual end lives on the OPEN session's ``ends_at``. Only ``end_at`` (→ session) and
    ``notes`` (→ reservation) may change.
    """
    session = (
        Session.objects.select_for_update()
        .filter(reservation=reservation, status=SessionStatus.OPEN)
        .first()
    )
    if session is None:
        raise ReservationConflictError("Active reservation has no open session.")

    new_end = validated_data.get("end_at")
    if new_end is not None:
        if new_end <= session.opened_at:
            raise ReservationConflictError("End time must be after the party was seated.")
        _check_reservation_conflict(
            restaurant_id=reservation.restaurant_id,
            table=session.table,
            start_at=session.opened_at,
            end_at=new_end,
            current_reservation_id=reservation.id,
        )
        session.ends_at = new_end
        session.save(update_fields=["ends_at", "updated_at"])

    if "notes" in validated_data:
        reservation.notes = validated_data["notes"]
        reservation.save(update_fields=["notes", "updated_at"])

    restaurant_id = reservation.restaurant_id
    table_id = str(session.table.public_id)
    transaction.on_commit(lambda: emit_hall_reservations_updated(restaurant_id, table_ids=[table_id]))

    return reservation


@transaction.atomic
def reschedule_reservation(
    reservation: Reservation,
    validated_data: dict[str, Any],
) -> Reservation:
    if reservation.status == ReservationStatus.ACTIVE:
        allowed = {"end_at", "notes"}
        disallowed = set(validated_data) - allowed
        if disallowed:
            raise ReservationConflictError(
                f"Active reservations can only be prolonged (end_at). Cannot change: {', '.join(sorted(disallowed))}."
            )
        return _prolong_active_reservation(reservation, validated_data)

    if reservation.status in {ReservationStatus.COMPLETED, ReservationStatus.CANCELLED}:
        raise ReservationConflictError(f"Cannot reschedule a {reservation.status} reservation.")

    old_table_public_id = str(reservation.table.public_id) if reservation.table else ""

    table = validated_data.get("table", reservation.table)
    if table is None:
        raise ReservationConflictError("Table not found or inactive.")
    table = Table.objects.select_for_update().get(id=table.id)

    start_at = validated_data.get("start_at", reservation.start_at)
    end_at = validated_data.get("end_at", reservation.end_at)

    settings = RestaurantSettings.objects.filter(restaurant_id=reservation.restaurant_id).first()
    if settings and settings.working_hours:
        tz = ZoneInfo(settings.timezone) if settings.timezone else ZoneInfo("UTC")
        local_start = start_at.astimezone(tz)
        day_key = _DAY_KEYS[local_start.weekday()]
        day_hours = settings.working_hours.get(day_key)
        if not day_hours:
            raise RestaurantClosedError(f"Restaurant closed on {day_key}.")
        open_min = _hhmm_to_minutes(day_hours.get("open"))
        close_min = _hhmm_to_minutes(day_hours.get("close"))
        if open_min is not None and close_min is not None:
            start_min = local_start.hour * 60 + local_start.minute
            local_end = end_at.astimezone(tz)
            end_min = local_end.hour * 60 + local_end.minute
            if close_min > open_min:
                if start_min < open_min or end_min > close_min:
                    raise RestaurantClosedError("Reservation falls outside operating hours.")
            else:
                if not (start_min >= open_min or start_min < close_min) or not (
                    end_min >= open_min or end_min < close_min
                ):
                    raise RestaurantClosedError("Reservation falls outside operating hours.")

    _check_reservation_conflict(
        restaurant_id=reservation.restaurant_id,
        table=table,
        start_at=start_at,
        end_at=end_at,
        current_reservation_id=reservation.id,
    )

    fields_to_update = ["table", "guest_count", "start_at", "end_at", "notes", "guest_name"]
    for field in fields_to_update:
        if field in validated_data:
            setattr(reservation, field, validated_data[field])

    reservation.save()

    # Notify the floor (waiter/booking views) so they refetch. Covers single-PATCH
    # reschedules; the batch path emits the same event from batch_update_reservations.
    restaurant_id = reservation.restaurant_id
    affected_table_ids = {old_table_public_id, str(reservation.table.public_id) if reservation.table else ""}
    transaction.on_commit(
        lambda: emit_hall_reservations_updated(restaurant_id, table_ids=list(affected_table_ids))
    )

    return reservation


ACTIVATION_EARLY_WINDOW = timedelta(minutes=15)  # how early a guest may self-activate


@transaction.atomic
def activate_reservation_by_scan(
    *,
    table: Table,
    user: Any,
) -> tuple[bool, str]:
    now = timezone.now()
    earliest_start = now - timedelta(minutes=30)  # allow up to 30 min late
    latest_start = now + timedelta(minutes=15)  # and up to 15 min early

    reservation = (
        Reservation.objects.select_for_update()
        .filter(
            table=table,
            status=ReservationStatus.PENDING,
            start_at__gte=earliest_start,
            start_at__lte=latest_start,
        )
        .first()
    )

    if not reservation:
        return False, "No imminent reservation found for this table."

    if not user.is_authenticated:
        return False, "Authentication required to activate this reservation."

    if reservation.customer_id != user.pk:
        return False, "This reservation belongs to another guest."

    reservation.status = ReservationStatus.ACTIVE
    reservation.save(update_fields=["status"])

    ensure_visit_session(reservation, opened_by=user)
    inject_preorders_for_reservation(reservation)

    restaurant_id = reservation.restaurant_id
    table_id = str(table.public_id)
    transaction.on_commit(
        lambda: emit_hall_reservations_updated(restaurant_id, table_ids=[table_id])
    )
    return True, "Table verified and activated."


_STATUS_TRANSITIONS: dict[str, set[str]] = {
    ReservationStatus.PENDING: {ReservationStatus.ACTIVE, ReservationStatus.CANCELLED},
    ReservationStatus.ACTIVE: {ReservationStatus.COMPLETED, ReservationStatus.CANCELLED},
}

_ALLOWED_ROLES: frozenset[str] = frozenset({RoleCode.ADMIN, RoleCode.WAITER})


@transaction.atomic
def update_reservation_status(
    reservation: Reservation,
    *,
    new_status: str,
    actor: User,
) -> Reservation:
    is_self_cancel = (
        new_status == ReservationStatus.CANCELLED
        and actor.role == RoleCode.CUSTOMER
        and reservation.customer_id == actor.pk
    )
    if not is_self_cancel and actor.role not in _ALLOWED_ROLES:
        raise PermissionDenied("Only admin and waiter roles may update reservation status.")

    allowed = _STATUS_TRANSITIONS.get(reservation.status, set())
    if new_status not in allowed:
        raise ReservationConflictError(f"Cannot transition reservation from '{reservation.status}' to '{new_status}'.")

    reservation.status = new_status
    reservation.save(update_fields=["status", "updated_at"])

    if new_status == ReservationStatus.CANCELLED and reservation.table is not None:
        table = reservation.table
        transaction.on_commit(
            lambda: emit_hall_reservation_cancelled(
                reservation.restaurant_id,
                reservation_id=str(reservation.public_id),
                table_id=str(table.public_id),
                actor=actor,
            )
        )

    table_id = str(reservation.table.public_id) if reservation.table else ""
    if table_id:
        transaction.on_commit(
            lambda: emit_hall_reservations_updated(reservation.restaurant_id, table_ids=[table_id])
        )

    return reservation


@transaction.atomic
def activate_pending_reservation(
    reservation: Reservation,
    *,
    actor: User,
) -> Reservation:
    if reservation.status == ReservationStatus.ACTIVE:
        return reservation

    if reservation.status != ReservationStatus.PENDING:
        raise ReservationConflictError("Only pending reservations can be activated.")

    table = reservation.table
    if table is None:
        raise ReservationConflictError("Reservation has no table assigned.")

    locked = Reservation.objects.select_for_update().get(pk=reservation.pk)

    if locked.status != ReservationStatus.PENDING:
        raise ReservationConflictError("Only pending reservations can be activated.")

    # Serialize concurrent activations onto this table. The open-session guard below
    # is a check-then-create: two activations of *different* pending reservations on
    # the same table lock different reservation rows, so without a per-table lock they
    # could both pass the guard and each open a session (double-booking). Locking the
    # table row forces them to run one at a time; the DB constraint
    # (orders_one_open_session_per_table) is the final backstop.
    Table.objects.select_for_update().get(pk=table.pk)

    now = timezone.now()
    grace_minutes = max(int(getattr(settings, "SESSION_OVERDUE_AUTO_CLOSE_MINUTES", 20)), 0)
    occupancy_cutoff = now - timedelta(minutes=grace_minutes)
    non_stale = Session.objects.filter(
        table=table,
        status=SessionStatus.OPEN,
        reservation__status=ReservationStatus.ACTIVE,
    ).annotate(
        effective_end_at=Coalesce("ends_at", "reservation__end_at"),
    ).filter(
        effective_end_at__gt=occupancy_cutoff,
    )
    if non_stale.exists():
        raise ReservationConflictError("Table already has an active session.")
    stale = Session.objects.filter(
        table=table,
        status=SessionStatus.OPEN,
        reservation__status=ReservationStatus.ACTIVE,
    ).annotate(
        effective_end_at=Coalesce("ends_at", "reservation__end_at"),
    ).filter(
        effective_end_at__lte=occupancy_cutoff,
    )
    for stale_session in stale:
        # force=True: this is automatic cleanup of a previous, unrelated
        # reservation's leftover session to make room for the one being
        # seated now. Without it, unserved items from that old session (e.g.
        # nobody clicked "served") raise UnservedItemsError here — blocking
        # staff from seating a brand-new party with a confusing error about
        # a booking they have nothing to do with.
        close_visit_session(session=stale_session, actor=None, force=True)

    # Floor the window at the no-show grace: a booking older than that is one
    # expire_noshow_reservations is about to clear, and must not take the table
    # out of service in the meantime. Without the floor a single PENDING row
    # that the sweep can't resolve blocks every later booking on this table.
    noshow_grace = max(int(getattr(settings, "RESERVATION_NO_SHOW_GRACE_MINUTES", 120)), 0)
    earlier_pending = (
        Reservation.objects.filter(
            restaurant_id=reservation.restaurant_id,
            table=table,
            status=ReservationStatus.PENDING,
            start_at__lt=reservation.start_at,
            start_at__lte=now,
            start_at__gt=now - timedelta(minutes=noshow_grace),
        )
        .exclude(id=reservation.id)
        .exists()
    )
    if earlier_pending:
        raise ReservationConflictError("There is an earlier pending reservation for this table.")

    locked.status = ReservationStatus.ACTIVE
    locked.save(update_fields=["status", "updated_at"])

    # Reuse ensure_visit_session rather than a raw Session.objects.create():
    # a paid pre-order (confirm_and_pay_preorder) can already have opened this
    # same reservation's Session while it was still PENDING — a bare .create()
    # would then hit either the reservation OneToOne constraint or
    # orders_one_open_session_per_table as a raw, unhandled IntegrityError.
    # ensure_visit_session is get-or-create and converts that constraint into
    # a friendly TableOccupiedError as a backstop.
    session = ensure_visit_session(locked, opened_by=actor)
    inject_preorders_for_reservation(locked)

    transaction.on_commit(
        lambda: emit_hall_table_status_changed(
            reservation.restaurant_id,
            table_id=str(table.public_id),
            previous_status="free",
            current_status="occupied",
            session_id=str(session.public_id),
            actor=actor,
        )
    )

    table_id = str(table.public_id)
    transaction.on_commit(
        lambda: emit_hall_reservations_updated(reservation.restaurant_id, table_ids=[table_id])
    )

    return locked


@transaction.atomic
def move_session_to_table(
    session: Session,
    *,
    new_table_id: str,
    actor: User,
) -> Session:
    if session.status != SessionStatus.OPEN:
        raise ReservationConflictError("Can only move an open session.")

    try:
        new_table = Table.objects.get(
            public_id=new_table_id,
            restaurant_id=session.restaurant_id,
            active=True,
        )
    except Table.DoesNotExist:
        raise NotFound("Target table not found or inactive.") from None

    if new_table.pk == session.table_id:
        raise ReservationConflictError("Session is already at this table.")

    now = timezone.now()
    reservation = session.reservation

    new_end_at = max(reservation.end_at, now + timedelta(hours=2))

    _check_reservation_conflict(
        restaurant_id=session.restaurant_id,
        table=new_table,
        start_at=now,
        end_at=new_end_at,
    )

    old_table = session.table
    reservation.status = ReservationStatus.CANCELLED
    reservation.save(update_fields=["status", "updated_at"])

    new_reservation = Reservation.objects.create(
        restaurant_id=session.restaurant_id,
        table=new_table,
        customer=reservation.customer,
        guest_count=session.guest_count,
        start_at=now,
        end_at=new_end_at,
        type=reservation.type,
        status=ReservationStatus.ACTIVE,
        created_by_staff=True,
        notes=f"Moved from table {session.table.public_number}",
    )

    session.table = new_table
    session.reservation = new_reservation
    session.save(update_fields=["table", "reservation", "updated_at"])

    transaction.on_commit(
        lambda: emit_hall_table_status_changed(
            session.restaurant_id,
            table_id=str(old_table.public_id),
            previous_status="occupied",
            current_status="free",
            session_id=str(session.public_id),
            actor=actor,
        )
    )

    transaction.on_commit(
        lambda: emit_hall_table_status_changed(
            session.restaurant_id,
            table_id=str(new_table.public_id),
            previous_status="free",
            current_status="occupied",
            session_id=str(session.public_id),
            actor=actor,
        )
    )

    affected_table_ids = [str(old_table.public_id), str(new_table.public_id)]
    transaction.on_commit(
        lambda: emit_hall_reservations_updated(session.restaurant_id, table_ids=affected_table_ids)
    )

    return session


@transaction.atomic
def close_session(
    session: Session,
    *,
    actor: User | None,
    force: bool = False,
) -> Session:
    if session.status != SessionStatus.OPEN:
        raise ReservationConflictError("Session is not open.")

    if not force:
        pending_items = OrderItem.objects.filter(
            order__session=session,
            status__in=[OrderItemStatus.PENDING, OrderItemStatus.IN_PROGRESS, OrderItemStatus.READY],
        ).exists()

        if pending_items:
            raise ReservationConflictError("Cannot close check: all items must be served or voided first.")

    session.status = SessionStatus.CLOSED
    session.save(update_fields=["status", "updated_at"])

    reservation = session.reservation
    if reservation.status == ReservationStatus.ACTIVE:
        reservation.status = ReservationStatus.COMPLETED
        now = timezone.now()
        reservation.end_at = now if now > reservation.start_at else reservation.start_at + timedelta(seconds=1)
        reservation.save(update_fields=["status", "end_at", "updated_at"])

    if actor is not None:
        transaction.on_commit(
            lambda: emit_hall_table_status_changed(
                session.restaurant_id,
                table_id=str(session.table.public_id),
                previous_status="occupied",
                current_status="free",
                session_id=str(session.public_id),
                actor=actor,
            )
        )

        table_id = str(session.table.public_id)
        transaction.on_commit(
            lambda: emit_hall_reservations_updated(session.restaurant_id, table_ids=[table_id])
        )

    return session


def _batch_end_date(c: dict[str, Any]) -> date:
    """Return end date, advanced by 1 day if the reservation crosses midnight."""
    if c["new_end_time"] <= c["new_start_time"]:
        return cast(date, c["new_date"] + timedelta(days=1))
    return cast(date, c["new_date"])


def _batch_active_end_datetime(c: dict[str, Any], session: Session) -> datetime:
    """End datetime for an ACTIVE row: anchored to session.opened_at.date().

    Consistent with ignoring the client's ``new_start_time`` (and therefore
    ``new_date``) for the start anchor — the seated party's actual times are
    the ground truth.
    """
    end_date = session.opened_at.date()
    opened_time = session.opened_at.time().replace(second=0, microsecond=0)
    if c["new_end_time"] <= opened_time:
        end_date += timedelta(days=1)
    return timezone.make_aware(datetime.combine(end_date, c["new_end_time"]))


@transaction.atomic
def batch_update_reservations(
    *,
    restaurant_id: int,
    changes: list[dict[str, Any]],
    cancellations: list[str] | None = None,
    actor: User | None = None,
) -> None:
    """Apply a batch of reservation moves/resizes/cancellations atomically.

    PENDING reservations are cancelled (status → CANCELLED); ACTIVE reservations
    are force-completed (session closed, status → COMPLETED). The entire batch
    rolls back on any failure.
    """
    # 1. Gather + lock all affected reservations
    res_public_ids = [c["reservation_id"] for c in changes]
    if cancellations:
        res_public_ids.extend(cancellations)

    reservations = Reservation.objects.select_for_update().filter(
        restaurant_id=restaurant_id,
        public_id__in=res_public_ids,
        status__in=[ReservationStatus.PENDING, ReservationStatus.ACTIVE],
    )
    res_map = {str(r.public_id): r for r in reservations}

    for c in changes:
        rid = str(c["reservation_id"])
        if rid not in res_map:
            raise NotFound(f"Reservation {rid} not found or not editable.")
    if cancellations:
        for c_id in cancellations:
            rid = str(c_id)
            if rid not in res_map:
                raise NotFound(f"Reservation {rid} not found or not editable.")

    # Validate no reservation is both changed AND cancelled
    change_ids = {c["reservation_id"] for c in changes}
    cancel_ids = set(cancellations or [])
    if change_ids & cancel_ids:
        raise ReservationConflictError("A reservation cannot be both modified and cancelled in the same batch.")

    # 2. Lock sessions for ACTIVE reservations (both changes and cancellations)
    session_map: dict[str, Session] = {}
    for c in changes:
        rid = str(c["reservation_id"])
        res = res_map[rid]
        if res.status == ReservationStatus.ACTIVE:
            session = (
                Session.objects.select_for_update()
                .filter(reservation=res, status=SessionStatus.OPEN)
                .first()
            )
            if session is None:
                raise ReservationConflictError(f"Active reservation {rid} has no open session.")
            session_map[rid] = session

    if cancellations:
        for c_id in cancellations:
            rid = str(c_id)
            res = res_map[rid]
            if res.status == ReservationStatus.ACTIVE:
                session = (
                    Session.objects.select_for_update()
                    .filter(reservation=res, status=SessionStatus.OPEN)
                    .first()
                )
                if session is None:
                    raise ReservationConflictError(f"Active reservation {rid} has no open session.")
                session_map[rid] = session

    # 3. Validation — past-date guard and overlap checks (applies to changes only)
    today = timezone.now().date()
    now_time = timezone.now().time().replace(second=0, microsecond=0)
    for c in changes:
        rid = str(c["reservation_id"])
        if res_map[rid].status == ReservationStatus.ACTIVE:
            continue
        if c["new_date"] < today:
            raise ReservationConflictError(
                "Cannot batch-update to a past date.",
                conflicting_reservation_id=rid,
            )
        if c["new_date"] == today and c["new_start_time"] < now_time:
            raise ReservationConflictError(
                "Cannot schedule a reservation in the past.",
                conflicting_reservation_id=rid,
            )

    intervals: list[tuple[str, datetime, datetime, str]] = []
    for c in changes:
        rid = str(c["reservation_id"])
        table_id = str(c["new_table_id"])
        if res_map[rid].status == ReservationStatus.ACTIVE:
            new_start = session_map[rid].opened_at
            new_end = _batch_active_end_datetime(c, session_map[rid])
        else:
            new_start = timezone.make_aware(datetime.combine(c["new_date"], c["new_start_time"]))
            new_end = timezone.make_aware(datetime.combine(_batch_end_date(c), c["new_end_time"]))
        if new_end <= new_start:
            raise ReservationConflictError(
                "Reservation end must be after its start.",
                conflicting_reservation_id=c["reservation_id"],
            )
        intervals.append((table_id, new_start, new_end, c["reservation_id"]))

    for i in range(len(intervals)):
        t_i, s_i, e_i, _rid_i = intervals[i]
        for j in range(i + 1, len(intervals)):
            t_j, s_j, e_j, rid_j = intervals[j]
            if t_i == t_j and s_i < e_j and s_j < e_i:
                raise ReservationConflictError(
                    "Overlapping reservations in payload.",
                    conflicting_reservation_id=rid_j,
                )

    for c in changes:
        rid = str(c["reservation_id"])
        res = res_map[rid]
        table = Table.objects.filter(
            public_id=c["new_table_id"],
            restaurant_id=restaurant_id,
            active=True,
        ).first()
        if table is None:
            raise NotFound(f"Table {c['new_table_id']} not found or inactive.")

        if res.status == ReservationStatus.ACTIVE:
            start_at = session_map[rid].opened_at
            end_at = _batch_active_end_datetime(c, session_map[rid])
            if end_at <= start_at:
                raise ReservationConflictError("End time must be after the party was seated.")
        else:
            start_at = timezone.make_aware(datetime.combine(c["new_date"], c["new_start_time"]))
            end_at = timezone.make_aware(datetime.combine(_batch_end_date(c), c["new_end_time"]))

        _check_reservation_conflict(
            restaurant_id=restaurant_id,
            table=table,
            start_at=start_at,
            end_at=end_at,
            current_reservation_id=res.id,
        )

    # 4. Apply all changes + cancellations
    affected_table_ids: set[str] = set()

    # Process cancellations first — pending become CANCELLED, active get force-completed
    if cancellations:
        for c_id in cancellations:
            rid = str(c_id)
            res = res_map[rid]
            if res.table:
                affected_table_ids.add(str(res.table.public_id))

            if res.status == ReservationStatus.ACTIVE:
                session = session_map[rid]
                close_session(session=session, actor=actor, force=True)
            else:
                res.status = ReservationStatus.CANCELLED
                res.save(update_fields=["status", "updated_at"])

            table = res.table
            if table is None and rid in session_map:
                table = session_map[rid].table
            if actor is not None and table is not None:

                def _cancel_hall_event(
                    reservation_id: str = str(res.public_id),
                    table_id: str = str(table.public_id),
                ) -> None:
                    emit_hall_reservation_cancelled(
                        restaurant_id,
                        reservation_id=reservation_id,
                        table_id=table_id,
                        actor=actor,
                    )

                transaction.on_commit(_cancel_hall_event)

    # Process moves/resizes
    for c in changes:
        rid = str(c["reservation_id"])
        res = res_map[rid]
        table = Table.objects.get(
            public_id=c["new_table_id"],
            restaurant_id=restaurant_id,
            active=True,
        )
        if res.status == ReservationStatus.ACTIVE:
            session = session_map[rid]
            old_table_id = str(session.table.public_id)
            affected_table_ids.update({old_table_id, str(c["new_table_id"])})
            session.ends_at = _batch_active_end_datetime(c, session)
            if old_table_id != str(c["new_table_id"]):
                session.table = table
            session.save(update_fields=["ends_at", "table", "updated_at"])
        else:
            affected_table_ids.update({str(res.table.public_id) if res.table else "", str(c["new_table_id"])})
            res.table = table
            res.start_at = timezone.make_aware(datetime.combine(c["new_date"], c["new_start_time"]))
            res.end_at = timezone.make_aware(datetime.combine(_batch_end_date(c), c["new_end_time"]))
            res.save(update_fields=["table", "start_at", "end_at", "updated_at"])

    # Aggregate refresh for affected tables after the batch lands.
    transaction.on_commit(lambda: emit_hall_reservations_updated(restaurant_id, table_ids=list(affected_table_ids)))
