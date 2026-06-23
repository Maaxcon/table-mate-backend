"""Walk-in reservation creation for the open-table flow."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Table
from common.exceptions import ReservationConflictError


@transaction.atomic
def create_walk_in_reservation(
    *,
    table: Table,
    guest_count: int,
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

    return Reservation.objects.create(
        table=table,
        restaurant_id=table.restaurant_id,
        guest_count=guest_count,
        start_at=now,
        end_at=end_at,
        type=ReservationType.WALK_IN,
        status=ReservationStatus.ACTIVE,
        customer=None,
    )
