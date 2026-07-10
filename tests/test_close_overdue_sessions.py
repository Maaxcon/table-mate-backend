from datetime import timedelta

import pytest
from django.utils import timezone

from apps.orders.models import Session, SessionStatus
from apps.orders.services import close_overdue_visit_sessions
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Restaurant, Table, Zone


def _table(restaurant: Restaurant, number: str) -> Table:
    zone, _ = Zone.objects.get_or_create(restaurant=restaurant, defaults={"name": "Main Hall"})
    return Table.objects.create(restaurant=restaurant, public_number=number, capacity=4, zone=zone, active=True)


def _active_reservation(
    restaurant: Restaurant,
    table: Table,
    *,
    end_offset: timedelta,
) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now - timedelta(hours=2),
        end_at=now + end_offset,
        status=ReservationStatus.ACTIVE,
        type=ReservationType.WALK_IN,
    )


@pytest.mark.django_db
def test_closes_session_overdue_beyond_grace(restaurant: Restaurant) -> None:
    reservation = _active_reservation(
        restaurant=restaurant,
        table=_table(restaurant, "S1"),
        end_offset=timedelta(minutes=-25),
    )
    session = Session.objects.create(
        restaurant=restaurant,
        table=reservation.table,
        reservation=reservation,
        guest_count=reservation.guest_count,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=reservation.start_at,
    )

    closed = close_overdue_visit_sessions()

    session.refresh_from_db()
    reservation.refresh_from_db()
    assert closed == 1
    assert session.status == SessionStatus.CLOSED
    assert reservation.status == ReservationStatus.COMPLETED


@pytest.mark.django_db
def test_keeps_session_within_overdue_grace(restaurant: Restaurant) -> None:
    reservation = _active_reservation(
        restaurant=restaurant,
        table=_table(restaurant, "S2"),
        end_offset=timedelta(minutes=-5),
    )
    session = Session.objects.create(
        restaurant=restaurant,
        table=reservation.table,
        reservation=reservation,
        guest_count=reservation.guest_count,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=reservation.start_at,
    )

    closed = close_overdue_visit_sessions()

    session.refresh_from_db()
    reservation.refresh_from_db()
    assert closed == 0
    assert session.status == SessionStatus.OPEN
    assert reservation.status == ReservationStatus.ACTIVE
