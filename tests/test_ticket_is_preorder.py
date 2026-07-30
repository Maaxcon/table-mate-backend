from datetime import timedelta
from typing import Any
from unittest import mock

import pytest
from django.utils import timezone

from apps.menu.models import MenuItem
from apps.orders.billing import checkout_cart_session, confirm_and_pay_preorder
from apps.orders.models import CartItem, CartSession, Ticket
from apps.orders.selectors import get_kitchen_tickets
from apps.orders.serializers import TicketSerializer
from apps.orders.services import ensure_active_cart_for_table, inject_scheduled_preorders
from apps.orders.services.cart import add_item_to_cart
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Restaurant, Table

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _restaurant_open() -> Any:
    with (
        mock.patch("apps.orders.services.cart.is_restaurant_open", return_value=True),
        mock.patch("apps.orders.billing.is_restaurant_open", return_value=True),
    ):
        yield


def _pending_reservation(restaurant: Restaurant, table: Table, *, start_offset: timedelta) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now + start_offset,
        end_at=now + start_offset + timedelta(hours=1),
        status=ReservationStatus.PENDING,
        type=ReservationType.PRE_BOOKED,
    )


def _preorder_cart(restaurant: Restaurant, reservation: Reservation, item: MenuItem) -> CartSession:
    cart = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
    CartItem.objects.create(restaurant=restaurant, cart_session=cart, menu_item=item, quantity=1, guest_slot=1)
    return cart


def test_preorder_ticket_is_flagged_after_injection(
    restaurant: Restaurant, table: Table, item: MenuItem
) -> None:
    reservation = _pending_reservation(restaurant, table, start_offset=timedelta(minutes=10))
    cart = _preorder_cart(restaurant, reservation, item)

    confirm_and_pay_preorder(cart_session=cart)
    injected = inject_scheduled_preorders()

    assert injected == 1
    ticket = Ticket.objects.get(order__session__reservation=reservation)
    data = TicketSerializer(ticket).data
    assert data["is_preorder"] is True


def test_regular_checkout_ticket_is_not_flagged(restaurant: Restaurant, table: Table, item: MenuItem) -> None:
    now = timezone.now()
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now - timedelta(minutes=10),
        end_at=now + timedelta(hours=1),
        status=ReservationStatus.ACTIVE,
        type=ReservationType.PRE_BOOKED,
    )
    cart = ensure_active_cart_for_table(table=table)
    add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=1)

    checkout_cart_session(cart_session=cart)

    ticket = Ticket.objects.get(order__session__reservation=reservation)
    data = TicketSerializer(ticket).data
    assert data["is_preorder"] is False


def test_kitchen_ticket_selector_annotates_is_preorder_via_serializer(
    restaurant: Restaurant, table: Table, item: MenuItem
) -> None:
    reservation = _pending_reservation(restaurant, table, start_offset=timedelta(minutes=5))
    cart = _preorder_cart(restaurant, reservation, item)
    confirm_and_pay_preorder(cart_session=cart)
    inject_scheduled_preorders()

    tickets = get_kitchen_tickets(restaurant.id)
    serialized = TicketSerializer(tickets, many=True).data
    assert len(serialized) == 1
    assert serialized[0]["is_preorder"] is True
