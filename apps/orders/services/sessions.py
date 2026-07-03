"""Cart-session lifecycle: open, ensure-for-table, stale cleanup, and auto-extend."""

import logging

from django.db import IntegrityError, transaction
from django.db.models import OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.authentication.models import User
from apps.reservations.models import Reservation, ReservationStatus
from apps.reservations.selectors import get_active_reservation_for_table
from apps.restaurants.models import Table
from apps.restaurants.selectors import get_working_hours_close_at
from common.exceptions import NoActiveReservationError, ReservationConflictError, ReservationNotFoundError
from common.hall_events import emit_hall_reservations_updated, emit_hall_session_auto_extended
from common.notification_events import emit_cart_created

from ..models import CartSession, CartSessionStatus, Session, SessionStatus
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


_STALE_CART_BATCH_SIZE = 500


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
    base = CartSession.objects.filter(status=CartSessionStatus.ACTIVE).filter(
        Q(reservation__status__in=[ReservationStatus.COMPLETED, ReservationStatus.CANCELLED])
        | Q(reservation__session__ends_at__lt=now)
        | Q(reservation__session__isnull=True, reservation__end_at__lt=now)
    )
    if restaurant_id is not None:
        base = base.filter(restaurant_id=restaurant_id)

    total_closed = 0
    while True:
        with transaction.atomic():
            batch = list(base.select_for_update(skip_locked=True).order_by("pk")[:batch_size])
            if not batch:
                break
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
    target_end: timezone.datetime,
) -> timezone.datetime | None:
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

    # Conflict found — find the earliest one
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
        )
        .filter(eff_start__gt=session.opened_at)
        .order_by("eff_start")
        .first()
    )
    if earliest is not None:
        return earliest.eff_start
    return None


def auto_extend_session(session: Session) -> dict[str, object]:
    """Attempt to extend an open session by up to 30 minutes.

    Respects working-hours boundaries (clamps to closing time) and upcoming
    reservation conflicts (clamps to the conflict's start). Returns a dict
    with ``extended`` (bool), ``clamped_by`` (str or None), and
    ``new_ends_at`` (datetime or None).
    """
    now = timezone.now()

    if session.ends_at is None or session.ends_at > now + timezone.timedelta(minutes=_AUTO_EXTEND_AHEAD_MINUTES):
        return {"extended": False, "clamped_by": None, "new_ends_at": None}

    target = now + timezone.timedelta(minutes=_AUTO_EXTEND_DURATION_MINUTES)
    reason: str | None = None

    # 1. Clamp to working hours
    close_at = get_working_hours_close_at(session.restaurant_id, now)
    if close_at is not None and target > close_at:
        target = close_at
        reason = "working_hours"

    # 2. Clamp to upcoming conflict
    conflict_limit = _find_conflict_limit(session, target)
    if conflict_limit is not None and conflict_limit < target:
        target = conflict_limit
        reason = "conflict"

    # 3. No meaningful extension
    if target <= session.ends_at:
        return {"extended": False, "clamped_by": reason, "new_ends_at": None}

    # 4. Apply
    session.ends_at = target
    session.save(update_fields=["ends_at", "updated_at"])

    restaurant_id = session.restaurant_id
    table_id = str(session.table.public_id)
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
        session.public_id,
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
    threshold = now + timezone.timedelta(minutes=_AUTO_EXTEND_AHEAD_MINUTES)

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
