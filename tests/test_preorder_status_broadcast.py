"""The guest's booking list learns about pre-order progress over the hall
stream, so "Being prepared" and "Ready" appear without a page reload.
"""

from datetime import timedelta
from typing import Any
from unittest import mock

import pytest
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.menu.models import MenuItem
from apps.orders.billing import confirm_and_pay_preorder
from apps.orders.models import CartItem, CartSession, OrderItem, OrderItemStatus
from apps.orders.services import inject_scheduled_preorders
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.reservations.selectors import preorder_status_for_reservation
from apps.restaurants.models import Restaurant, Table

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _restaurant_open() -> Any:
    with (
        mock.patch("apps.orders.services.cart.is_restaurant_open", return_value=True),
        mock.patch("apps.orders.billing.is_restaurant_open", return_value=True),
    ):
        yield


def _paid_preorder(restaurant: Restaurant, table: Table, item: MenuItem) -> Reservation:
    now = timezone.now()
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now + timedelta(minutes=10),
        end_at=now + timedelta(hours=1),
        status=ReservationStatus.PENDING,
        type=ReservationType.PRE_BOOKED,
    )
    cart = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
    CartItem.objects.create(
        restaurant=restaurant, cart_session=cart, menu_item=item, quantity=1, guest_slot=1
    )
    confirm_and_pay_preorder(cart_session=cart)
    return reservation


def test_paid_preorder_reports_paid_before_the_kitchen_sees_it(
    restaurant: Restaurant, table: Table, item: MenuItem
) -> None:
    reservation = _paid_preorder(restaurant, table, item)

    assert preorder_status_for_reservation(reservation.pk) == "paid"


def test_a_booking_without_a_preorder_has_no_status(restaurant: Restaurant, table: Table) -> None:
    now = timezone.now()
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now + timedelta(minutes=10),
        end_at=now + timedelta(hours=1),
        status=ReservationStatus.PENDING,
    )

    assert preorder_status_for_reservation(reservation.pk) is None


def test_handing_the_round_to_the_kitchen_announces_cooking(
    restaurant: Restaurant, table: Table, item: MenuItem, django_capture_on_commit_callbacks: Any
) -> None:
    reservation = _paid_preorder(restaurant, table, item)

    with (
        mock.patch("common.hall_events.emit_hall_preorder_status_changed") as emit,
        django_capture_on_commit_callbacks(execute=True),
    ):
        assert inject_scheduled_preorders() == 1

    emit.assert_called_once_with(
        restaurant.id,
        reservation_id=str(reservation.public_id),
        status="cooking",
    )


def test_the_last_item_turning_ready_announces_ready(
    restaurant: Restaurant,
    table: Table,
    item: MenuItem,
    api: Any,
    django_capture_on_commit_callbacks: Any,
) -> None:
    reservation = _paid_preorder(restaurant, table, item)
    inject_scheduled_preorders()
    order_item = OrderItem.objects.get(order__session__reservation=reservation)

    cook = api(role=RoleCode.COOK, restaurant_id=restaurant.id)
    with (
        mock.patch("common.hall_events.emit_hall_preorder_status_changed") as emit,
        django_capture_on_commit_callbacks(execute=True),
    ):
        resp = cook.client.patch(
            f"/api/orders/order-items/{order_item.public_id}/",
            {"status": OrderItemStatus.READY},
            format="json",
        )

    assert resp.status_code == status.HTTP_200_OK
    emit.assert_called_once_with(
        restaurant.id,
        reservation_id=str(reservation.public_id),
        status="ready",
    )
