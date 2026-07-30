from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.menu.models import MenuItem
from apps.orders.models import (
    Order,
    OrderItem,
    OrderItemStatus,
    OrderPaymentStatus,
    Session,
    SessionStatus,
    Ticket,
    TicketStatus,
)
from apps.reservations.models import Reservation, ReservationStatus
from apps.reservations.selectors import _annotate_has_preorder
from apps.restaurants.models import Restaurant, Table

pytestmark = pytest.mark.django_db


def _reservation(restaurant: Restaurant, table: Table) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now + timedelta(minutes=15),
        end_at=now + timedelta(hours=2),
        status=ReservationStatus.PENDING,
    )


def _session(restaurant: Restaurant, table: Table, reservation: Reservation) -> Session:
    return Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=reservation.guest_count,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=timezone.now(),
        ends_at=reservation.end_at,
    )


def _paid_order(restaurant: Restaurant, session: Session) -> Order:
    return Order.objects.create(
        restaurant=restaurant,
        session=session,
        currency="UAH",
        payment_status=OrderPaymentStatus.PAID,
        total_amount=Decimal("100.00"),
    )


def _item(restaurant: Restaurant, order: Order, menu_item: MenuItem, status_: str) -> OrderItem:
    return OrderItem.objects.create(
        restaurant=restaurant,
        order=order,
        menu_item=menu_item,
        guest_slot=1,
        quantity=1,
        status=status_,
        unit_price=menu_item.price,
        total_price=menu_item.price,
        is_paid=True,
    )


def _ticket(restaurant: Restaurant, session: Session, order: Order) -> Ticket:
    return Ticket.objects.create(
        restaurant=restaurant,
        session=session,
        order=order,
        status=TicketStatus.INCOMING,
        injected_at=timezone.now(),
    )


def _flags(reservation: Reservation) -> tuple[bool, bool, bool]:
    row = _annotate_has_preorder(Reservation.objects.filter(pk=reservation.pk)).first()
    assert row is not None
    return row.has_preorder, row.preorder_cooking, row.preorder_ready


def test_paid_but_not_yet_injected_is_not_cooking_or_ready(
    restaurant: Restaurant, table: Table, item: MenuItem
) -> None:
    reservation = _reservation(restaurant, table)
    session = _session(restaurant, table, reservation)
    order = _paid_order(restaurant, session)
    _item(restaurant, order, item, OrderItemStatus.PENDING)
    # No Ticket yet — inject_scheduled_preorders hasn't run.

    has_preorder, cooking, ready = _flags(reservation)
    assert has_preorder is True
    assert cooking is False
    assert ready is False


def test_ticket_injected_with_unfinished_items_is_cooking_not_ready(
    restaurant: Restaurant, table: Table, item: MenuItem
) -> None:
    reservation = _reservation(restaurant, table)
    session = _session(restaurant, table, reservation)
    order = _paid_order(restaurant, session)
    _item(restaurant, order, item, OrderItemStatus.IN_PROGRESS)
    _ticket(restaurant, session, order)

    has_preorder, cooking, ready = _flags(reservation)
    assert has_preorder is True
    assert cooking is True
    assert ready is False


def test_all_items_ready_flips_to_ready(restaurant: Restaurant, table: Table, item: MenuItem) -> None:
    reservation = _reservation(restaurant, table)
    session = _session(restaurant, table, reservation)
    order = _paid_order(restaurant, session)
    _item(restaurant, order, item, OrderItemStatus.READY)
    _ticket(restaurant, session, order)

    has_preorder, cooking, ready = _flags(reservation)
    assert has_preorder is True
    assert cooking is True
    assert ready is True


def test_one_item_still_pending_keeps_it_cooking(restaurant: Restaurant, table: Table, item: MenuItem) -> None:
    reservation = _reservation(restaurant, table)
    session = _session(restaurant, table, reservation)
    order = _paid_order(restaurant, session)
    _item(restaurant, order, item, OrderItemStatus.READY)
    _item(restaurant, order, item, OrderItemStatus.PENDING)
    _ticket(restaurant, session, order)

    has_preorder, cooking, ready = _flags(reservation)
    assert cooking is True
    assert ready is False


def test_reservation_list_endpoint_exposes_preorder_ready(
    restaurant: Restaurant, table: Table, item: MenuItem, api: Any
) -> None:
    reservation = _reservation(restaurant, table)
    session = _session(restaurant, table, reservation)
    order = _paid_order(restaurant, session)
    _item(restaurant, order, item, OrderItemStatus.READY)
    _ticket(restaurant, session, order)

    waiter = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
    resp = waiter.client.get(
        "/api/reservations/reservations/", {"status__in": "pending,active"}
    )
    assert resp.status_code == status.HTTP_200_OK
    payload = resp.json()
    results = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
    row = next(r for r in results if r["public_id"] == str(reservation.public_id))
    assert row["has_preorder"] is True
    assert row["preorder_cooking"] is True
    assert row["preorder_ready"] is True
