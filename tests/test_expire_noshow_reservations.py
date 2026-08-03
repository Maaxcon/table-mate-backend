import concurrent.futures
import threading
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.db import connection, transaction
from django.utils import timezone

from apps.menu.models import MenuItem
from apps.orders.models import (
    Order,
    OrderItem,
    OrderItemStatus,
    OrderPaymentStatus,
    OrderSource,
    Session,
    SessionStatus,
    Ticket,
    TicketStatus,
)
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.reservations.services import expire_noshow_reservations
from apps.restaurants.models import Restaurant, RestaurantSettings, Table

pytestmark = pytest.mark.django_db


def _pending_reservation(
    restaurant: Restaurant, table: Table, *, start_offset: timedelta, duration: timedelta = timedelta(hours=2)
) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now + start_offset,
        end_at=now + start_offset + duration,
        status=ReservationStatus.PENDING,
        type=ReservationType.PRE_BOOKED,
    )


def test_expires_reservation_past_grace(restaurant: Restaurant, table: Table) -> None:
    reservation = _pending_reservation(restaurant, table, start_offset=timedelta(minutes=-150))

    expired = expire_noshow_reservations()

    reservation.refresh_from_db()
    assert expired == 1
    assert reservation.status == ReservationStatus.CANCELLED


def test_keeps_reservation_within_grace(restaurant: Restaurant, table: Table) -> None:
    reservation = _pending_reservation(restaurant, table, start_offset=timedelta(minutes=-10))

    expired = expire_noshow_reservations()

    reservation.refresh_from_db()
    assert expired == 0
    assert reservation.status == ReservationStatus.PENDING


def test_ignores_non_pending_reservations(restaurant: Restaurant, table: Table) -> None:
    reservation = _pending_reservation(restaurant, table, start_offset=timedelta(minutes=-150))
    reservation.status = ReservationStatus.ACTIVE
    reservation.save(update_fields=["status"])

    expired = expire_noshow_reservations()

    reservation.refresh_from_db()
    assert expired == 0
    assert reservation.status == ReservationStatus.ACTIVE


def test_cancels_unstarted_paid_preorder_along_with_the_reservation(
    restaurant: Restaurant, table: Table, item: MenuItem
) -> None:
    # Payment here is simulated, so an unstarted (no kitchen Ticket) pre-order
    # gets refunded and swept up with the no-show, same as one with no pre-order.
    reservation = _pending_reservation(restaurant, table, start_offset=timedelta(minutes=-150))
    session = Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=reservation.guest_count,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=timezone.now(),
        ends_at=reservation.end_at,
    )
    order = Order.objects.create(
        restaurant=restaurant,
        session=session,
        currency="UAH",
        source=OrderSource.CUSTOMER_PREORDER,
        payment_status=OrderPaymentStatus.PAID,
        total_amount=Decimal("100.00"),
    )
    OrderItem.objects.create(
        restaurant=restaurant,
        order=order,
        menu_item=item,
        guest_slot=1,
        quantity=1,
        status=OrderItemStatus.READY,
        unit_price=item.price,
        total_price=item.price,
        is_paid=True,
    )

    expired = expire_noshow_reservations()

    reservation.refresh_from_db()
    order.refresh_from_db()
    assert expired == 1
    assert reservation.status == ReservationStatus.CANCELLED
    assert order.payment_status == OrderPaymentStatus.REFUNDED


def _cooked_preorder_noshow(
    restaurant: Restaurant, table: Table, item: MenuItem
) -> tuple[Reservation, Session, Order, Ticket, OrderItem]:
    """A no-show whose paid pre-order the kitchen already picked up."""
    reservation = _pending_reservation(restaurant, table, start_offset=timedelta(minutes=-150))
    session = Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=reservation.guest_count,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=timezone.now(),
        ends_at=reservation.end_at,
    )
    order = Order.objects.create(
        restaurant=restaurant,
        session=session,
        currency="UAH",
        source=OrderSource.CUSTOMER_PREORDER,
        payment_status=OrderPaymentStatus.PAID,
        total_amount=Decimal("100.00"),
    )
    order_item = OrderItem.objects.create(
        restaurant=restaurant,
        order=order,
        menu_item=item,
        guest_slot=1,
        quantity=1,
        status=OrderItemStatus.IN_PROGRESS,
        unit_price=item.price,
        total_price=item.price,
        is_paid=True,
    )
    ticket = Ticket.objects.create(
        restaurant=restaurant,
        session=session,
        order=order,
        status=TicketStatus.INCOMING,
        injected_at=timezone.now(),
    )
    # _inject_preorder_orders attaches the ticket to the order's items.
    OrderItem.objects.filter(order=order).update(ticket=ticket)
    order_item.refresh_from_db()
    return reservation, session, order, ticket, order_item


def test_cooked_preorder_noshow_is_completed_not_refunded(
    restaurant: Restaurant, table: Table, item: MenuItem
) -> None:
    # The kitchen already cooked this food, so there is nothing to refund —
    # but the booking still has to reach a terminal status, or it blocks the
    # table for every later booking.
    reservation, session, order, ticket, order_item = _cooked_preorder_noshow(restaurant, table, item)

    expired = expire_noshow_reservations()

    reservation.refresh_from_db()
    order.refresh_from_db()
    session.refresh_from_db()
    ticket.refresh_from_db()
    order_item.refresh_from_db()
    assert expired == 1
    assert reservation.status == ReservationStatus.COMPLETED
    assert order.payment_status == OrderPaymentStatus.PAID
    assert session.status == SessionStatus.CLOSED
    # Off the kitchen board, rather than sitting INCOMING forever.
    assert ticket.status == TicketStatus.BUMPED
    assert order_item.status == OrderItemStatus.VOIDED


def test_cooked_preorder_noshow_stops_blocking_the_table(
    restaurant: Restaurant, table: Table, item: MenuItem, user_factory: Any
) -> None:
    from apps.authentication.models import RoleCode
    from apps.reservations.services import activate_pending_reservation

    _cooked_preorder_noshow(restaurant, table, item)
    expire_noshow_reservations()

    actor = user_factory(role=RoleCode.WAITER)
    actor.save()
    tonight = _pending_reservation(restaurant, table, start_offset=timedelta(minutes=-5))

    activate_pending_reservation(tonight, actor=actor)

    tonight.refresh_from_db()
    assert tonight.status == ReservationStatus.ACTIVE


def test_closes_lingering_session_when_expiring(restaurant: Restaurant, table: Table) -> None:
    # A PENDING reservation can already have opened its Session (e.g. an
    # unpaid draft cart) — expiring it must not leave that session dangling.
    reservation = _pending_reservation(restaurant, table, start_offset=timedelta(minutes=-150))
    session = Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=reservation.guest_count,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=timezone.now(),
        ends_at=reservation.end_at,
    )

    expired = expire_noshow_reservations()

    reservation.refresh_from_db()
    session.refresh_from_db()
    assert expired == 1
    assert reservation.status == ReservationStatus.CANCELLED
    assert session.status == SessionStatus.CLOSED


def test_unblocks_later_reservation_on_same_table(
    restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings, user_factory: Any
) -> None:
    from apps.authentication.models import RoleCode
    from apps.reservations.services import activate_pending_reservation

    actor = user_factory(role=RoleCode.WAITER)
    actor.save()
    stale = _pending_reservation(
        restaurant, table, start_offset=timedelta(minutes=-150), duration=timedelta(minutes=20)
    )
    later = _pending_reservation(restaurant, table, start_offset=timedelta(minutes=-5))

    expire_noshow_reservations()

    stale.refresh_from_db()
    assert stale.status == ReservationStatus.CANCELLED

    result = activate_pending_reservation(later, actor=actor)
    assert result.status == ReservationStatus.ACTIVE


@pytest.mark.django_db(transaction=True)
def test_never_cancels_a_reservation_being_seated_concurrently(
    restaurant: Restaurant, table: Table
) -> None:
    # Regression: expire_noshow_reservations used to read status=PENDING
    # unlocked, then call cancel_reservation separately — which also accepts
    # ACTIVE (it's shared with staff cancelling a seated party). A guest
    # seated in that gap would get cancelled right back out. The fix locks
    # the whole batch (skip_locked) before deciding, so a row being seated
    # concurrently is skipped this run instead of wrongly cancelled.
    reservation = _pending_reservation(restaurant, table, start_offset=timedelta(minutes=-150))

    lock_acquired = threading.Event()
    proceed_to_commit = threading.Event()

    def _seat_concurrently() -> None:
        with transaction.atomic():
            locked = Reservation.objects.select_for_update().get(pk=reservation.pk)
            lock_acquired.set()
            proceed_to_commit.wait(timeout=5)
            locked.status = ReservationStatus.ACTIVE
            locked.save(update_fields=["status"])
        connection.close()

    def _run_expiry() -> int:
        assert lock_acquired.wait(timeout=5)
        result = expire_noshow_reservations()
        proceed_to_commit.set()
        connection.close()
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        seat_future = pool.submit(_seat_concurrently)
        expire_future = pool.submit(_run_expiry)
        expired_count = expire_future.result(timeout=10)
        seat_future.result(timeout=10)

    reservation.refresh_from_db()
    assert expired_count == 0
    assert reservation.status == ReservationStatus.ACTIVE
