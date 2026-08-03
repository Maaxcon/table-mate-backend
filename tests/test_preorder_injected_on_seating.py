"""Seating a party must hand the kitchen any pre-order it hasn't cooked yet.

inject_scheduled_preorders only sweeps PENDING reservations due within
PREORDER_LEAD_MINUTES (20). Staff seating has no early window, so a party
seated 45 minutes ahead of its booking went ACTIVE before the sweep ever
matched the order: the guest had paid, the kitchen never saw the food, and the
never-served items then blocked close_visit_session at the end of the visit.
"""

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.authentication.models import RoleCode
from apps.menu.models import MenuItem
from apps.orders.billing import confirm_and_pay_preorder
from apps.orders.models import CartItem, CartSession, Order, OrderItem, Ticket
from apps.orders.services.sessions import inject_scheduled_preorders
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.reservations.services import activate_pending_reservation, activate_reservation_by_scan
from apps.restaurants.models import Restaurant, Table

pytestmark = pytest.mark.django_db

# Comfortably outside PREORDER_LEAD_MINUTES, so the sweep will not match.
AHEAD_OF_SWEEP = timedelta(minutes=45)


def _pending_reservation(
    restaurant: Restaurant, table: Table, *, start_offset: timedelta, customer: Any = None
) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        customer=customer,
        guest_count=2,
        start_at=now + start_offset,
        end_at=now + start_offset + timedelta(hours=1),
        status=ReservationStatus.PENDING,
        type=ReservationType.PRE_BOOKED,
    )


def _pay_preorder(restaurant: Restaurant, reservation: Reservation, item: MenuItem) -> Order:
    cart = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
    CartItem.objects.create(
        restaurant=restaurant, cart_session=cart, menu_item=item, quantity=1, guest_slot=1
    )
    confirm_and_pay_preorder(cart_session=cart)
    return Order.objects.get(session__reservation=reservation)


def test_staff_seating_early_hands_the_preorder_to_the_kitchen(
    restaurant: Restaurant, table: Table, item: MenuItem, user_factory: Any
) -> None:
    actor = user_factory(role=RoleCode.WAITER)
    actor.save()
    reservation = _pending_reservation(restaurant, table, start_offset=AHEAD_OF_SWEEP)
    order = _pay_preorder(restaurant, reservation, item)
    assert inject_scheduled_preorders() == 0

    activate_pending_reservation(reservation, actor=actor)

    ticket = Ticket.objects.get(order=order)
    assert OrderItem.objects.filter(order=order, ticket=ticket).count() == 1


def test_guest_self_seating_hands_the_preorder_to_the_kitchen(
    restaurant: Restaurant, table: Table, item: MenuItem, user_factory: Any
) -> None:
    customer = user_factory(role=RoleCode.CUSTOMER)
    customer.save()
    reservation = _pending_reservation(
        restaurant, table, start_offset=timedelta(minutes=10), customer=customer
    )
    order = _pay_preorder(restaurant, reservation, item)

    activated, _message = activate_reservation_by_scan(table=table, user=customer)

    assert activated is True
    assert Ticket.objects.filter(order=order).exists()


def test_seating_does_not_double_ticket_an_already_injected_preorder(
    restaurant: Restaurant, table: Table, item: MenuItem, user_factory: Any
) -> None:
    actor = user_factory(role=RoleCode.WAITER)
    actor.save()
    reservation = _pending_reservation(restaurant, table, start_offset=timedelta(minutes=10))
    order = _pay_preorder(restaurant, reservation, item)
    assert inject_scheduled_preorders() == 1

    activate_pending_reservation(reservation, actor=actor)

    assert Ticket.objects.filter(order=order).count() == 1
