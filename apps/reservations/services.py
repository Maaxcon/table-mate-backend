from datetime import date, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.authentication.models import RoleCode, User
from apps.orders.billing import ensure_visit_session
from apps.orders.models import OrderItem, OrderItemStatus, Session, SessionStatus
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
    if qs.exists():
        raise ReservationConflictError("Table is not available during the requested time.")

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
    if seated.exists():
        raise ReservationConflictError(
            "Table is occupied; a new reservation must start after the seated party."
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

    staff_notes = f"Guest: {guest_name}"
    if guest_phone:
        staff_notes += f", Phone: {guest_phone}"
    if notes:
        staff_notes += f"\n{notes}"

    reservation = Reservation.objects.create(
        restaurant_id=restaurant_id,
        customer=None,
        customer_name=guest_name,
        table=table,
        guest_count=guest_count,
        start_at=start_at,
        end_at=end_at,
        type=ReservationType.PRE_BOOKED,
        status=ReservationStatus.PENDING,
        created_by_staff=True,
        notes=staff_notes,
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
def cancel_reservation(reservation: Reservation) -> Reservation:
    """Cancel a pending or active reservation. Rejects any other state.

    Mirrors reschedule/activate: the state-machine lives here, not in the view.
    """
    locked = Reservation.objects.select_for_update().get(pk=reservation.pk)
    if locked.status not in {ReservationStatus.PENDING, ReservationStatus.ACTIVE}:
        raise ReservationCancelError("Only pending or active reservations can be cancelled.")
    locked.status = ReservationStatus.CANCELLED
    locked.save(update_fields=["status"])
    return locked


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

    fields_to_update = ["table", "guest_count", "start_at", "end_at", "notes"]
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


def activate_reservation(
    *,
    reservation: Reservation,
    opened_by: Any = None,
    enforce_window: bool = False,
) -> Reservation:
    """Flip a pending reservation to active (staff or the owning customer).

    No QR is needed; the waiter or the owning customer opens the table on
    arrival. Staff have no time limit. When enforce_window is set (customer
    self-activation) the booking can only be activated near its start — not more
    than ACTIVATION_EARLY_WINDOW early — so a guest cannot open a far-future
    booking. Arriving late is always allowed.
    Idempotent if already active; rejects completed/cancelled reservations.
    Opens the visit Session (bill) so the floor plan shows the table occupied.
    """
    opened_by_user = opened_by if (opened_by is not None and opened_by.is_authenticated) else None
    with transaction.atomic():
        locked = Reservation.objects.select_for_update().get(pk=reservation.pk)
        if locked.status not in {ReservationStatus.PENDING, ReservationStatus.ACTIVE}:
            raise ReservationConflictError("Only pending reservations can be activated.")
        if locked.status == ReservationStatus.PENDING:
            if enforce_window and locked.start_at - timezone.now() > ACTIVATION_EARLY_WINDOW:
                raise ReservationConflictError("This reservation cannot be activated yet.")
            locked.status = ReservationStatus.ACTIVE
            locked.save(update_fields=["status"])
        ensure_visit_session(locked, opened_by=opened_by_user)

    restaurant_id = locked.restaurant_id
    table_id = str(locked.table.public_id) if locked.table else ""
    if table_id:
        transaction.on_commit(
            lambda: emit_hall_reservations_updated(restaurant_id, table_ids=[table_id])
        )
    return locked


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

    if Session.objects.filter(table=table, status=SessionStatus.OPEN).exists():
        raise ReservationConflictError("Table already has an active session.")

    now = timezone.now()
    earlier_pending = (
        Reservation.objects.filter(
            restaurant_id=reservation.restaurant_id,
            table=table,
            status=ReservationStatus.PENDING,
            start_at__lt=reservation.start_at,
            start_at__lte=now,
        )
        .exclude(id=reservation.id)
        .exists()
    )
    if earlier_pending:
        raise ReservationConflictError("There is an earlier pending reservation for this table.")

    locked.status = ReservationStatus.ACTIVE
    locked.save(update_fields=["status", "updated_at"])

    restaurant = table.restaurant
    try:
        currency = restaurant.settings.currency
    except RestaurantSettings.DoesNotExist:
        currency = "UAH"
    session = Session.objects.create(
        restaurant_id=reservation.restaurant_id,
        table=table,
        reservation=locked,
        opened_by=actor,
        guest_count=reservation.guest_count,
        currency=currency,
        opened_at=now,
        ends_at=locked.end_at,
    )

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
    actor: User,
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
        reservation.end_at = timezone.now()
        reservation.save(update_fields=["status", "end_at", "updated_at"])

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
        raise ValidationError("A reservation cannot be both modified and cancelled in the same batch.")

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
        if res_map[str(c["reservation_id"])].status == ReservationStatus.ACTIVE:
            continue
        if c["new_date"] < today:
            raise ValidationError("Cannot batch-update to a past date.")
        if c["new_date"] == today and c["new_start_time"] < now_time:
            raise ValidationError("Cannot schedule a reservation in the past.")

    intervals: list[tuple[str, datetime, datetime, str]] = []
    for c in changes:
        rid = str(c["reservation_id"])
        table_id = str(c["new_table_id"])
        new_end = timezone.make_aware(datetime.combine(_batch_end_date(c), c["new_end_time"]))
        if res_map[rid].status == ReservationStatus.ACTIVE:
            new_start = session_map[rid].opened_at
        else:
            new_start = timezone.make_aware(datetime.combine(c["new_date"], c["new_start_time"]))
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

        end_at = timezone.make_aware(datetime.combine(_batch_end_date(c), c["new_end_time"]))
        if res.status == ReservationStatus.ACTIVE:
            start_at = session_map[rid].opened_at
            if end_at <= start_at:
                raise ReservationConflictError("End time must be after the party was seated.")
        else:
            start_at = timezone.make_aware(datetime.combine(c["new_date"], c["new_start_time"]))

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

    # Process moves/resizes
    for c in changes:
        rid = str(c["reservation_id"])
        res = res_map[rid]
        table = Table.objects.get(
            public_id=c["new_table_id"],
            restaurant_id=restaurant_id,
            active=True,
        )
        new_end = timezone.make_aware(datetime.combine(_batch_end_date(c), c["new_end_time"]))

        if res.status == ReservationStatus.ACTIVE:
            session = session_map[rid]
            old_table_id = str(session.table.public_id)
            affected_table_ids.update({old_table_id, str(c["new_table_id"])})
            session.ends_at = new_end
            if old_table_id != str(c["new_table_id"]):
                session.table = table
            session.save(update_fields=["ends_at", "table", "updated_at"])
        else:
            affected_table_ids.update({str(res.table.public_id) if res.table else "", str(c["new_table_id"])})
            res.table = table
            res.start_at = timezone.make_aware(datetime.combine(c["new_date"], c["new_start_time"]))
            res.end_at = new_end
            res.save(update_fields=["table", "start_at", "end_at", "updated_at"])

    # Also broadcast table-status events for force-closed sessions
    transaction.on_commit(lambda: emit_hall_reservations_updated(restaurant_id, table_ids=list(affected_table_ids)))
