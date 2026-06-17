from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.orders.models import CartSession, CartSessionStatus
from apps.orders.services import close_stale_cart_sessions
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Restaurant, Table


def _table(restaurant: Restaurant, number: str) -> Table:
    return Table.objects.create(restaurant=restaurant, table_number=number, capacity=4, active=True)


def _reservation(
    restaurant: Restaurant,
    table: Table,
    *,
    status: str,
    end_offset: timedelta,
) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now - timedelta(hours=2),
        end_at=now + end_offset,
        status=status,
        type=ReservationType.PRE_BOOKED,
    )


def _active_cart(restaurant: Restaurant, reservation: Reservation) -> CartSession:
    return CartSession.objects.create(restaurant=restaurant, reservation=reservation)


@pytest.mark.django_db
def test_closes_cart_of_completed_reservation(restaurant: Restaurant) -> None:
    res = _reservation(
        restaurant, _table(restaurant, "C1"), status=ReservationStatus.COMPLETED, end_offset=timedelta(hours=1)
    )
    cart = _active_cart(restaurant, res)

    closed = close_stale_cart_sessions()

    cart.refresh_from_db()
    assert closed == 1
    assert cart.status == CartSessionStatus.CLOSED


@pytest.mark.django_db
def test_closes_cart_of_cancelled_reservation(restaurant: Restaurant) -> None:
    res = _reservation(
        restaurant, _table(restaurant, "C2"), status=ReservationStatus.CANCELLED, end_offset=timedelta(hours=1)
    )
    cart = _active_cart(restaurant, res)

    close_stale_cart_sessions()

    cart.refresh_from_db()
    assert cart.status == CartSessionStatus.CLOSED


@pytest.mark.django_db
def test_closes_cart_of_expired_active_reservation(restaurant: Restaurant) -> None:
    # Still ACTIVE by status but the visit window has already ended.
    res = _reservation(
        restaurant, _table(restaurant, "C3"), status=ReservationStatus.ACTIVE, end_offset=timedelta(hours=-1)
    )
    cart = _active_cart(restaurant, res)

    close_stale_cart_sessions()

    cart.refresh_from_db()
    assert cart.status == CartSessionStatus.CLOSED


@pytest.mark.django_db
def test_keeps_cart_of_active_valid_reservation(restaurant: Restaurant) -> None:
    res = _reservation(
        restaurant, _table(restaurant, "C4"), status=ReservationStatus.ACTIVE, end_offset=timedelta(hours=1)
    )
    cart = _active_cart(restaurant, res)

    closed = close_stale_cart_sessions()

    cart.refresh_from_db()
    assert closed == 0
    assert cart.status == CartSessionStatus.ACTIVE


@pytest.mark.django_db
def test_count_reflects_only_newly_closed(restaurant: Restaurant) -> None:
    stale_res = _reservation(
        restaurant, _table(restaurant, "C5"), status=ReservationStatus.COMPLETED, end_offset=timedelta(hours=1)
    )
    _active_cart(restaurant, stale_res)
    # An already-closed cart must not be re-counted.
    closed_res = _reservation(
        restaurant, _table(restaurant, "C6"), status=ReservationStatus.COMPLETED, end_offset=timedelta(hours=1)
    )
    CartSession.objects.create(restaurant=restaurant, reservation=closed_res, status=CartSessionStatus.CLOSED)
    # A healthy active cart stays untouched.
    live_res = _reservation(
        restaurant, _table(restaurant, "C7"), status=ReservationStatus.ACTIVE, end_offset=timedelta(hours=1)
    )
    _active_cart(restaurant, live_res)

    closed = close_stale_cart_sessions()

    assert closed == 1
    assert CartSession.objects.filter(status=CartSessionStatus.ACTIVE).count() == 1


@pytest.mark.django_db
def test_management_command_closes_and_reports(restaurant: Restaurant) -> None:
    res = _reservation(
        restaurant, _table(restaurant, "C8"), status=ReservationStatus.COMPLETED, end_offset=timedelta(hours=1)
    )
    cart = _active_cart(restaurant, res)

    out = StringIO()
    call_command("close_stale_carts", stdout=out)

    cart.refresh_from_db()
    assert cart.status == CartSessionStatus.CLOSED
    assert "Closed 1 stale cart session(s)." in out.getvalue()
