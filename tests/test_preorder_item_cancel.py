"""A guest changing their mind about one dish shouldn't have to cancel the
whole pre-order and pay for it again.
"""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.menu.models import MenuItem
from apps.orders.billing import cancel_preorder_item, confirm_and_pay_preorder
from apps.orders.models import (
    CartItem,
    CartSession,
    Order,
    OrderItem,
    OrderItemStatus,
    OrderPaymentStatus,
    OrderStatus,
    Ticket,
    TicketStatus,
)
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.reservations.selectors import preorder_window_open
from apps.restaurants.models import Restaurant, RestaurantSettings, Table
from common.exceptions import PreorderNotAllowedError

pytestmark = pytest.mark.django_db


def _reservation(restaurant: Restaurant, table: Table, customer: Any = None) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        customer=customer,
        guest_count=2,
        start_at=now + timedelta(minutes=30),
        end_at=now + timedelta(hours=2),
        status=ReservationStatus.PENDING,
        type=ReservationType.PRE_BOOKED,
    )


def _pay_round(restaurant: Restaurant, reservation: Reservation, item: MenuItem, dishes: int) -> Order:
    # One cart line per menu item (orders_cartitem_unique_session_item), so a
    # second dish means a second menu item.
    cart = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
    menu_items = [item] + [
        MenuItem.objects.create(
            restaurant=restaurant,
            menu=item.menu,
            category=item.category,
            name=f"Side {n}",
            price=Decimal("12.5000"),
            sort_order=100 + n,
            is_available=True,
        )
        for n in range(dishes - 1)
    ]
    for slot, menu_item in enumerate(menu_items):
        CartItem.objects.create(
            restaurant=restaurant,
            cart_session=cart,
            menu_item=menu_item,
            quantity=1,
            guest_slot=slot + 1,
        )
    confirm_and_pay_preorder(cart_session=cart)
    order = Order.objects.filter(session__reservation=reservation).order_by("pk").last()
    assert order is not None
    return order


def test_removing_one_dish_refunds_only_that_dish(
    restaurant: Restaurant,
    table: Table,
    item: MenuItem,
    restaurant_settings: RestaurantSettings,
) -> None:
    reservation = _reservation(restaurant, table)
    order = _pay_round(restaurant, reservation, item, dishes=2)
    before = order.total_amount
    dish = OrderItem.objects.filter(order=order).order_by("pk").first()
    assert dish is not None

    cancel_preorder_item(order_item=dish)

    order.refresh_from_db()
    dish.refresh_from_db()
    assert dish.status == OrderItemStatus.VOIDED
    assert dish.is_paid is False
    assert order.payment_status == OrderPaymentStatus.PAID
    assert Decimal("0") < order.total_amount < before
    # The check still adds up after the service charge was spread again.
    survivor = OrderItem.objects.filter(order=order).exclude(status=OrderItemStatus.VOIDED).get()
    assert order.total_amount == survivor.total_price + order.tax_total + order.service_charge


def test_removing_the_last_dish_cancels_the_whole_round(
    restaurant: Restaurant, table: Table, item: MenuItem, restaurant_settings: RestaurantSettings
) -> None:
    reservation = _reservation(restaurant, table)
    order = _pay_round(restaurant, reservation, item, dishes=1)
    dish = OrderItem.objects.get(order=order)

    cancel_preorder_item(order_item=dish)

    order.refresh_from_db()
    assert order.status == OrderStatus.CANCELLED
    assert order.payment_status == OrderPaymentStatus.REFUNDED
    assert order.total_amount == Decimal("0")


def test_a_dish_the_kitchen_already_has_cannot_be_removed(
    restaurant: Restaurant, table: Table, item: MenuItem, restaurant_settings: RestaurantSettings
) -> None:
    reservation = _reservation(restaurant, table)
    order = _pay_round(restaurant, reservation, item, dishes=2)
    Ticket.objects.create(
        restaurant=restaurant,
        session=order.session,
        order=order,
        status=TicketStatus.INCOMING,
        injected_at=timezone.now(),
    )
    dish = OrderItem.objects.filter(order=order).order_by("pk").first()
    assert dish is not None

    with pytest.raises(PreorderNotAllowedError):
        cancel_preorder_item(order_item=dish)

    dish.refresh_from_db()
    assert dish.status != OrderItemStatus.VOIDED


def test_the_owner_removes_a_dish_through_the_api(
    restaurant: Restaurant,
    table: Table,
    item: MenuItem,
    restaurant_settings: RestaurantSettings,
    api: Any,
) -> None:
    owner = api(role=RoleCode.CUSTOMER)
    reservation = _reservation(restaurant, table, customer=owner.user)
    order = _pay_round(restaurant, reservation, item, dishes=2)
    dish = OrderItem.objects.filter(order=order).order_by("pk").first()
    assert dish is not None

    resp = owner.client.delete(
        f"/api/reservations/reservations/{reservation.public_id}/preorder/items/{dish.public_id}/"
    )

    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["public_id"] != str(dish.public_id)


def test_removing_the_last_dish_through_the_api_answers_no_content(
    restaurant: Restaurant,
    table: Table,
    item: MenuItem,
    restaurant_settings: RestaurantSettings,
    api: Any,
) -> None:
    owner = api(role=RoleCode.CUSTOMER)
    reservation = _reservation(restaurant, table, customer=owner.user)
    order = _pay_round(restaurant, reservation, item, dishes=1)
    dish = OrderItem.objects.get(order=order)

    resp = owner.client.delete(
        f"/api/reservations/reservations/{reservation.public_id}/preorder/items/{dish.public_id}/"
    )

    assert resp.status_code == status.HTTP_204_NO_CONTENT


def test_someone_elses_booking_is_not_found(
    restaurant: Restaurant,
    table: Table,
    item: MenuItem,
    restaurant_settings: RestaurantSettings,
    api: Any,
) -> None:
    owner = api(role=RoleCode.CUSTOMER)
    stranger = api(role=RoleCode.CUSTOMER)
    reservation = _reservation(restaurant, table, customer=owner.user)
    order = _pay_round(restaurant, reservation, item, dishes=2)
    dish = OrderItem.objects.filter(order=order).order_by("pk").first()
    assert dish is not None

    resp = stranger.client.delete(
        f"/api/reservations/reservations/{reservation.public_id}/preorder/items/{dish.public_id}/"
    )

    assert resp.status_code == status.HTTP_404_NOT_FOUND
    dish.refresh_from_db()
    assert dish.status != OrderItemStatus.VOIDED


def test_adding_a_round_is_refused_once_the_kitchen_window_opens(
    restaurant: Restaurant, table: Table, item: MenuItem, restaurant_settings: RestaurantSettings
) -> None:
    # PREORDER_LEAD_MINUTES (20) before the start the sweep hands the food to
    # the kitchen, so a further round would arrive out of step with the rest.
    now = timezone.now()
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now + timedelta(minutes=10),
        end_at=now + timedelta(hours=2),
        status=ReservationStatus.PENDING,
        type=ReservationType.PRE_BOOKED,
    )
    cart = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
    CartItem.objects.create(
        restaurant=restaurant, cart_session=cart, menu_item=item, quantity=1, guest_slot=1
    )

    with pytest.raises(PreorderNotAllowedError):
        confirm_and_pay_preorder(cart_session=cart)

    assert not preorder_window_open(reservation)


def test_the_window_is_open_for_a_booking_further_out(
    restaurant: Restaurant, table: Table
) -> None:
    now = timezone.now()
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now + timedelta(hours=3),
        end_at=now + timedelta(hours=5),
        status=ReservationStatus.PENDING,
        type=ReservationType.PRE_BOOKED,
    )

    assert preorder_window_open(reservation)


def test_the_check_says_when_adding_is_over(
    restaurant: Restaurant,
    table: Table,
    item: MenuItem,
    restaurant_settings: RestaurantSettings,
    api: Any,
) -> None:
    owner = api(role=RoleCode.CUSTOMER)
    reservation = _reservation(restaurant, table, customer=owner.user)
    _pay_round(restaurant, reservation, item, dishes=2)

    resp = owner.client.get(f"/api/reservations/reservations/{reservation.public_id}/preorder/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["can_add_more"] is True

    Reservation.objects.filter(pk=reservation.pk).update(start_at=timezone.now() + timedelta(minutes=5))
    resp = owner.client.get(f"/api/reservations/reservations/{reservation.public_id}/preorder/")
    assert resp.json()["can_add_more"] is False
