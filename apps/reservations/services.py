from datetime import datetime, timedelta
from typing import Any

from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.db.models.functions import Greatest
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.authentication.models import RoleCode, User
from apps.orders.billing import ensure_visit_session
from apps.orders.models import OrderItem, OrderItemStatus, Session, SessionStatus
from apps.restaurants.models import Table
from common.exceptions import ReservationCancelError, ReservationConflictError
from common.hall_events import (
    emit_hall_new_reservation,
    emit_hall_reservation_cancelled,
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
    active_session_subquery = (
        Session.objects.filter(
            reservation=OuterRef("pk"),
            status=SessionStatus.OPEN,
        )
        .order_by("opened_at")
        .values("opened_at")[:1]
    )

    qs = (
        Reservation.objects.filter(
            restaurant_id=restaurant_id,
            table=table,
            status__in=[ReservationStatus.PENDING, ReservationStatus.ACTIVE],
        )
        .annotate(effective_start=Greatest("start_at", Subquery(active_session_subquery)))
        .filter(
            effective_start__lt=end_at,
            end_at__gt=start_at,
        )
    )
    if current_reservation_id is not None:
        qs = qs.exclude(id=current_reservation_id)
    if qs.exists():
        raise ReservationConflictError("Table is not available during the requested time.")


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
            table_number=table.table_number,
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
            table_number=table.table_number,
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


@transaction.atomic
def reschedule_reservation(
    reservation: Reservation,
    validated_data: dict[str, Any],
) -> Reservation:
    table = validated_data.get("table", reservation.table)
    if table is None:
        raise ReservationConflictError("Table not found or inactive.")
    table = Table.objects.select_for_update().get(id=table.id)

    start_at = validated_data.get("start_at", reservation.start_at)
    end_at = validated_data.get("end_at", reservation.end_at)

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

    return reservation


@transaction.atomic
def activate_pending_reservation(
    reservation: Reservation,
    *,
    actor: User,
) -> Reservation:
    if reservation.status != ReservationStatus.PENDING:
        raise ReservationConflictError("Only pending reservations can be activated.")

    table = reservation.table
    if table is None:
        raise ReservationConflictError("Reservation has no table assigned.")

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

    reservation.status = ReservationStatus.ACTIVE
    reservation.save(update_fields=["status", "updated_at"])

    restaurant = table.restaurant
    session = Session.objects.create(
        restaurant_id=reservation.restaurant_id,
        table=table,
        reservation=reservation,
        opened_by=actor,
        guest_count=reservation.guest_count,
        currency=restaurant.settings.currency,
        opened_at=now,
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

    return reservation


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

    return session


@transaction.atomic
def close_session(
    session: Session,
    *,
    actor: User,
) -> Session:
    if session.status != SessionStatus.OPEN:
        raise ReservationConflictError("Session is not open.")

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

    return session
