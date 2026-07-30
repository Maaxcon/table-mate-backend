from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

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


def test_skips_reservation_whose_preorder_kitchen_already_started(
    restaurant: Restaurant, table: Table, item: MenuItem
) -> None:
    # A Ticket exists — real food is already being cooked, so this one is left
    # for a human instead of being auto-cancelled.
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
        payment_status=OrderPaymentStatus.PAID,
        total_amount=Decimal("100.00"),
    )
    OrderItem.objects.create(
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
    Ticket.objects.create(
        restaurant=restaurant,
        session=session,
        order=order,
        status=TicketStatus.INCOMING,
        injected_at=timezone.now(),
    )

    expired = expire_noshow_reservations()

    reservation.refresh_from_db()
    order.refresh_from_db()
    assert expired == 0
    assert reservation.status == ReservationStatus.PENDING
    assert order.payment_status == OrderPaymentStatus.PAID


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
