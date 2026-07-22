from datetime import timedelta

import pytest
from django.utils import timezone

from apps.orders.models import Session, SessionStatus
from apps.orders.services import auto_extend_session
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Restaurant, Table, Zone


def _table(restaurant: Restaurant, number: str) -> Table:
    zone, _ = Zone.objects.get_or_create(restaurant=restaurant, defaults={"name": "Main Hall"})
    return Table.objects.create(restaurant=restaurant, public_number=number, capacity=4, zone=zone, active=True)


def _open_session_near_end(restaurant: Restaurant, table: Table, *, end_offset: timedelta) -> Session:
    now = timezone.now()
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now - timedelta(hours=1),
        end_at=now + end_offset,
        status=ReservationStatus.ACTIVE,
        type=ReservationType.WALK_IN,
    )
    return Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=reservation.guest_count,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=reservation.start_at,
        ends_at=reservation.end_at,
    )


@pytest.mark.django_db
def test_extends_once_when_nearing_end(restaurant: Restaurant) -> None:
    session = _open_session_near_end(restaurant, _table(restaurant, "A1"), end_offset=timedelta(minutes=5))
    original_ends_at = session.ends_at

    result = auto_extend_session(session)

    session.refresh_from_db()
    assert result["extended"] is True
    assert session.auto_extended is True
    assert session.ends_at > original_ends_at


@pytest.mark.django_db
def test_does_not_extend_twice(restaurant: Restaurant) -> None:
    session = _open_session_near_end(restaurant, _table(restaurant, "A2"), end_offset=timedelta(minutes=5))
    auto_extend_session(session)
    session.refresh_from_db()
    extended_ends_at = session.ends_at

    result = auto_extend_session(session)

    session.refresh_from_db()
    assert result["extended"] is False
    assert session.ends_at == extended_ends_at
