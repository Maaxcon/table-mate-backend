"""Cancelling a multi-round pre-order must refund all rounds or none.

The cancel loop refunded each round in turn and raised on the first one the
kitchen had already ticketed. With no ATOMIC_REQUESTS that partial work stuck:
the guest read "couldn't cancel" while an earlier round sat cancelled,
refunded and zeroed. expire_noshow_reservations had the same shape, over an
unordered queryset, so which round died was up to the database.
"""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from apps.authentication.models import RoleCode
from apps.menu.models import MenuItem
from apps.orders.billing import confirm_and_pay_preorder
from apps.orders.models import (
    CartItem,
    CartSession,
    Order,
    OrderItemStatus,
    OrderPaymentStatus,
    Ticket,
    TicketStatus,
)
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.reservations.services import expire_noshow_reservations
from apps.restaurants.models import Restaurant, Table
from common.exceptions import PreorderNotAllowedError

pytestmark = pytest.mark.django_db


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


def _pay_round(restaurant: Restaurant, reservation: Reservation, item: MenuItem) -> Order:
    cart = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
    CartItem.objects.create(
        restaurant=restaurant, cart_session=cart, menu_item=item, quantity=1, guest_slot=1
    )
    confirm_and_pay_preorder(cart_session=cart)
    return Order.objects.filter(session__reservation=reservation).order_by("pk").last()


def _ticket(order: Order) -> Ticket:
    return Ticket.objects.create(
        restaurant=order.restaurant,
        session=order.session,
        order=order,
        status=TicketStatus.INCOMING,
        injected_at=timezone.now(),
    )


def test_a_ticketed_round_leaves_every_other_round_untouched(
    restaurant: Restaurant, table: Table, item: MenuItem
) -> None:
    reservation = _pending_reservation(restaurant, table, start_offset=timedelta(hours=3))
    first = _pay_round(restaurant, reservation, item)
    second = _pay_round(restaurant, reservation, item)
    _ticket(second)

    from apps.orders.billing import cancel_preorder_rounds

    with pytest.raises(PreorderNotAllowedError):
        cancel_preorder_rounds(orders=[first, second])

    first.refresh_from_db()
    assert first.payment_status == OrderPaymentStatus.PAID
    assert first.total_amount > Decimal("0")
    assert not first.items.filter(status=OrderItemStatus.VOIDED).exists()


def test_untouched_rounds_are_all_cancelled_together(
    restaurant: Restaurant, table: Table, item: MenuItem
) -> None:
    reservation = _pending_reservation(restaurant, table, start_offset=timedelta(hours=3))
    first = _pay_round(restaurant, reservation, item)
    second = _pay_round(restaurant, reservation, item)

    from apps.orders.billing import cancel_preorder_rounds

    cancel_preorder_rounds(orders=[first, second])

    for order in (first, second):
        order.refresh_from_db()
        assert order.payment_status == OrderPaymentStatus.REFUNDED
        assert order.total_amount == Decimal("0")


def test_no_show_sweep_keeps_a_partly_cooked_booking_whole(
    restaurant: Restaurant, table: Table, item: MenuItem, settings: Any
) -> None:
    settings.RESERVATION_NO_SHOW_GRACE_MINUTES = 0
    reservation = _pending_reservation(restaurant, table, start_offset=-timedelta(hours=3))
    first = _pay_round(restaurant, reservation, item)
    second = _pay_round(restaurant, reservation, item)
    _ticket(second)

    assert expire_noshow_reservations() == 1

    first.refresh_from_db()
    second.refresh_from_db()
    reservation.refresh_from_db()
    # One round was cooked, so no round is refunded — all or nothing.
    assert first.payment_status == OrderPaymentStatus.PAID
    assert second.payment_status == OrderPaymentStatus.PAID
    # But the booking still closes out, or it blocks the table for good.
    assert reservation.status == ReservationStatus.COMPLETED


def test_no_show_sweep_refunds_every_round_when_the_kitchen_has_none(
    restaurant: Restaurant, table: Table, item: MenuItem, settings: Any
) -> None:
    settings.RESERVATION_NO_SHOW_GRACE_MINUTES = 0
    reservation = _pending_reservation(restaurant, table, start_offset=-timedelta(hours=3))
    first = _pay_round(restaurant, reservation, item)
    second = _pay_round(restaurant, reservation, item)

    assert expire_noshow_reservations() == 1

    for order in (first, second):
        order.refresh_from_db()
        assert order.payment_status == OrderPaymentStatus.REFUNDED
    reservation.refresh_from_db()
    assert reservation.status == ReservationStatus.CANCELLED


def test_cancelling_from_the_api_is_rejected_whole(
    restaurant: Restaurant, table: Table, item: MenuItem, api: Any, user_factory: Any
) -> None:
    customer = user_factory(role=RoleCode.CUSTOMER)
    customer.save()
    reservation = _pending_reservation(restaurant, table, start_offset=timedelta(hours=3))
    reservation.customer = customer
    reservation.save(update_fields=["customer"])
    first = _pay_round(restaurant, reservation, item)
    second = _pay_round(restaurant, reservation, item)
    _ticket(second)

    ctx = api(role=RoleCode.CUSTOMER)
    ctx.client.force_authenticate(user=customer)
    response = ctx.client.delete(f"/api/reservations/reservations/{reservation.public_id}/preorder/")

    assert response.status_code == 409
    first.refresh_from_db()
    assert first.payment_status == OrderPaymentStatus.PAID
