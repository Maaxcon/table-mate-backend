from datetime import timedelta

import pytest
from django.utils import timezone

from apps.orders.models import Session, SessionStatus
from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import Restaurant, Table
from apps.restaurants.selectors import get_tables_with_occupancy


@pytest.mark.django_db
def test_table_occupancy_tracks_session_ends_at_not_booked_end(restaurant: Restaurant, table: Table) -> None:
    now = timezone.now()
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now - timedelta(hours=2),
        end_at=now - timedelta(minutes=5),
        status=ReservationStatus.ACTIVE,
    )
    Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=reservation.guest_count,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=reservation.start_at,
        ends_at=now + timedelta(minutes=20),
    )

    occupied = get_tables_with_occupancy(restaurant.id).get(pk=table.pk)

    assert occupied.is_occupied is True
