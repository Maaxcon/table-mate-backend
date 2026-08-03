"""Closing a check anyway must clear what it skipped off the kitchen board.

force=True skipped the unserved-items guard but cleaned up nothing behind it:
the items stayed PENDING/IN_PROGRESS and their Ticket stayed live, so a visit
that had already ended kept sitting on the kitchen board. Those tickets never
reach COMPLETED either, so the completed column's day filter never aged them
out — and force_close_shift_end_sessions runs nightly.
"""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from apps.authentication.models import RoleCode
from apps.menu.models import MenuItem
from apps.orders.billing import close_visit_session
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
from apps.orders.selectors import get_kitchen_tickets
from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import Restaurant, Table
from common.exceptions import UnservedItemsError

pytestmark = pytest.mark.django_db


def _seated(restaurant: Restaurant, table: Table) -> Session:
    now = timezone.now()
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now - timedelta(minutes=30),
        end_at=now + timedelta(minutes=30),
        status=ReservationStatus.ACTIVE,
    )
    return Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=2,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=now,
        ends_at=reservation.end_at,
    )


def _ticketed_item(
    restaurant: Restaurant, session: Session, menu_item: MenuItem, item_status: str
) -> tuple[OrderItem, Ticket]:
    order = Order.objects.create(
        restaurant=restaurant,
        session=session,
        currency="UAH",
        payment_status=OrderPaymentStatus.PAID,
        total_amount=Decimal("100.00"),
    )
    ticket = Ticket.objects.create(
        restaurant=restaurant,
        session=session,
        order=order,
        status=TicketStatus.ACTIVE,
        injected_at=timezone.now(),
    )
    item = OrderItem.objects.create(
        restaurant=restaurant,
        order=order,
        menu_item=menu_item,
        ticket=ticket,
        guest_slot=1,
        quantity=1,
        status=item_status,
        unit_price=menu_item.price,
        total_price=menu_item.price,
    )
    return item, ticket


def test_force_close_voids_leftovers_and_bumps_their_tickets(
    restaurant: Restaurant, table: Table, item: MenuItem, user_factory: Any
) -> None:
    staff = user_factory(role=RoleCode.WAITER)
    staff.save()
    session = _seated(restaurant, table)
    order_item, ticket = _ticketed_item(restaurant, session, item, OrderItemStatus.IN_PROGRESS)

    close_visit_session(session=session, actor=staff, force=True)

    order_item.refresh_from_db()
    ticket.refresh_from_db()
    assert order_item.status == OrderItemStatus.VOIDED
    assert ticket.status == TicketStatus.BUMPED


def test_a_force_closed_visit_leaves_the_kitchen_board(
    restaurant: Restaurant, table: Table, item: MenuItem, user_factory: Any
) -> None:
    staff = user_factory(role=RoleCode.WAITER)
    staff.save()
    session = _seated(restaurant, table)
    _ticketed_item(restaurant, session, item, OrderItemStatus.PENDING)

    close_visit_session(session=session, actor=staff, force=True)

    for column in (TicketStatus.INCOMING, TicketStatus.ACTIVE, TicketStatus.COMPLETED):
        assert not get_kitchen_tickets(restaurant.id, status=column).exists()


def test_closing_normally_still_refuses_while_food_is_out(
    restaurant: Restaurant, table: Table, item: MenuItem, user_factory: Any
) -> None:
    staff = user_factory(role=RoleCode.WAITER)
    staff.save()
    session = _seated(restaurant, table)
    order_item, ticket = _ticketed_item(restaurant, session, item, OrderItemStatus.IN_PROGRESS)

    with pytest.raises(UnservedItemsError):
        close_visit_session(session=session, actor=staff)

    order_item.refresh_from_db()
    ticket.refresh_from_db()
    assert order_item.status == OrderItemStatus.IN_PROGRESS
    assert ticket.status == TicketStatus.ACTIVE


def test_force_close_leaves_served_items_and_finished_tickets_alone(
    restaurant: Restaurant, table: Table, item: MenuItem, user_factory: Any
) -> None:
    staff = user_factory(role=RoleCode.WAITER)
    staff.save()
    session = _seated(restaurant, table)
    served, served_ticket = _ticketed_item(restaurant, session, item, OrderItemStatus.SERVED)
    served_ticket.status = TicketStatus.COMPLETED
    served_ticket.save(update_fields=["status"])
    _ticketed_item(restaurant, session, item, OrderItemStatus.PENDING)

    close_visit_session(session=session, actor=staff, force=True)

    served.refresh_from_db()
    served_ticket.refresh_from_db()
    assert served.status == OrderItemStatus.SERVED
    assert served_ticket.status == TicketStatus.COMPLETED
