from datetime import datetime, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.authentication.models import User
from apps.orders.billing import ensure_visit_session
from apps.orders.models import Session
from apps.restaurants.models import Table
from common.exceptions import ReservationConflictError

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
    qs = Reservation.objects.filter(
        restaurant_id=restaurant_id,
        table=table,
        status__in=[ReservationStatus.PENDING, ReservationStatus.ACTIVE],
        start_at__lt=end_at,
        end_at__gt=start_at,
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

    return reservation


@transaction.atomic
def seat_walk_in_customer(
    table: Table,
    guest_count: int,
    opened_by: User | None = None,
) -> Reservation:
    now = timezone.now()
    default_end = now + timedelta(hours=2)

    next_reservation = (
        Reservation.objects.filter(
            table=table,
            restaurant_id=table.restaurant_id,
            status__in=[ReservationStatus.PENDING, ReservationStatus.ACTIVE],
            end_at__gt=now,
        )
        .order_by("start_at")
        .first()
    )

    if next_reservation is not None:
        end_at = min(default_end, next_reservation.start_at)
    else:
        end_at = default_end

    if end_at <= now:
        raise ReservationConflictError("Table has no available time for a walk-in reservation.")

    reservation = Reservation.objects.create(
        table=table,
        restaurant_id=table.restaurant_id,
        guest_count=guest_count,
        start_at=now,
        end_at=end_at,
        type=ReservationType.WALK_IN,
        status=ReservationStatus.ACTIVE,
        customer=None,
    )

    restaurant = table.restaurant
    Session.objects.create(
        restaurant_id=table.restaurant_id,
        table=table,
        reservation=reservation,
        opened_by=opened_by,
        guest_count=guest_count,
        currency=restaurant.settings.currency,
        opened_at=now,
    )

    return reservation


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
