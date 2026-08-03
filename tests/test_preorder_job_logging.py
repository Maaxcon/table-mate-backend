"""The unattended pre-order jobs must not move money or cancel bookings silently.

inject_scheduled_preorders and expire_noshow_reservations run on a timer with
no user watching. When a guest asks why their pre-order vanished, or why the
kitchen never got it, these lines are the only record there is.
"""

import logging
from datetime import timedelta
from typing import Any
from unittest import mock

import pytest
from django.utils import timezone

from apps.menu.models import MenuItem
from apps.orders.billing import cancel_preorder, confirm_and_pay_preorder
from apps.orders.models import CartItem, CartSession, Order
from apps.orders.services import inject_scheduled_preorders
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.reservations.services import expire_noshow_reservations
from apps.restaurants.models import Restaurant, Table

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _restaurant_open() -> Any:
    with (
        mock.patch("apps.orders.services.cart.is_restaurant_open", return_value=True),
        mock.patch("apps.orders.billing.is_restaurant_open", return_value=True),
    ):
        yield


def _paid_preorder(
    restaurant: Restaurant, table: Table, item: MenuItem, *, start_offset: timedelta
) -> tuple[Reservation, Order]:
    now = timezone.now()
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now + start_offset,
        end_at=now + start_offset + timedelta(hours=1),
        status=ReservationStatus.PENDING,
        type=ReservationType.PRE_BOOKED,
    )
    cart = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
    CartItem.objects.create(
        restaurant=restaurant, cart_session=cart, menu_item=item, quantity=1, guest_slot=1
    )
    confirm_and_pay_preorder(cart_session=cart)
    return reservation, Order.objects.get(session__reservation=reservation)


def test_refunding_a_preorder_is_recorded(
    restaurant: Restaurant, table: Table, item: MenuItem, caplog: Any
) -> None:
    _reservation, order = _paid_preorder(restaurant, table, item, start_offset=timedelta(hours=5))

    with caplog.at_level(logging.INFO, logger="apps.orders.billing"):
        cancel_preorder(order=order)

    assert str(order.public_id) in caplog.text
    assert "Refunded" in caplog.text


def test_handing_a_preorder_to_the_kitchen_is_recorded(
    restaurant: Restaurant, table: Table, item: MenuItem, caplog: Any
) -> None:
    _reservation, order = _paid_preorder(restaurant, table, item, start_offset=timedelta(minutes=10))

    with caplog.at_level(logging.INFO, logger="apps.orders.services.sessions"):
        assert inject_scheduled_preorders() == 1

    assert str(order.public_id) in caplog.text


def test_expiring_a_no_show_is_recorded(
    restaurant: Restaurant, table: Table, item: MenuItem, caplog: Any, settings: Any
) -> None:
    settings.RESERVATION_NO_SHOW_GRACE_MINUTES = 0
    reservation, _order = _paid_preorder(restaurant, table, item, start_offset=-timedelta(hours=3))

    with caplog.at_level(logging.INFO):
        assert expire_noshow_reservations() == 1

    assert str(reservation.public_id) in caplog.text
    # The refund the sweep triggered is recorded too, not just the expiry.
    assert "Refunded" in caplog.text
