from datetime import datetime

from django.db import transaction

from apps.restaurants.models import Table, TableStatus
from common.exceptions import ReservationConflictError

from ..editor.selectors import get_available_tables
from .models import Reservation, ReservationStatus


def check_availability(
    restaurant_id: int,
    table_id: str,
    start_at: datetime,
    end_at: datetime,
) -> bool:
    available = get_available_tables(
        restaurant_id=restaurant_id,
        start_at=start_at,
        end_at=end_at,
    )
    return available.filter(public_id=table_id).exists()


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
        raise ReservationConflictError("Table not found or inactive.")

    overlapping = Reservation.objects.filter(
        restaurant_id=restaurant_id,
        table=table,
        status=ReservationStatus.CONFIRMED,
        start_at__lt=end_at,
        end_at__gt=start_at,
    ).select_for_update()

    if overlapping.exists():
        raise ReservationConflictError("Table is not available during the requested time.")

    reservation = Reservation.objects.create(
        restaurant_id=restaurant_id,
        customer_id=customer_id,
        table=table,
        guest_count=guest_count,
        start_at=start_at,
        end_at=end_at,
        status=ReservationStatus.CONFIRMED,
        notes=notes or "",
    )

    table.status = TableStatus.RESERVED
    table.save(update_fields=["status", "updated_at"])

    return reservation
