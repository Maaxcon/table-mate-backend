"""A paid pre-order must not occupy its table before the party arrives.

Regression for unibrix/table-mate-backend#69: confirm_and_pay_preorder used to
call ensure_visit_session, opening the visit Session with opened_at=now the
moment the guest paid. A booking three weeks out therefore took its table out of
service immediately — orders_one_open_session_per_table blocked seating anyone
else on it, while the floor plan still drew the table as free, so staff only
found out via a TableOccupiedError that never stopped being true.
"""

from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.authentication.models import RoleCode
from apps.menu.models import MenuItem
from apps.orders.billing import checkout_cart_session, confirm_and_pay_preorder
from apps.orders.models import (
    CartItem,
    CartSession,
    OrderPaymentStatus,
    Session,
    SessionStatus,
    Ticket,
)
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.reservations.selectors import get_unavailable_table_ids
from apps.reservations.services import activate_pending_reservation, cancel_reservation
from apps.restaurants.models import Restaurant, RestaurantSettings, Table
from common.exceptions import ReservationNotYetActiveError

pytestmark = pytest.mark.django_db

WEEKS_OUT = timedelta(weeks=3)


def _pending_reservation(
    restaurant: Restaurant,
    table: Table,
    *,
    start_offset: timedelta,
    customer: Any = None,
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


def _pay_preorder(restaurant: Restaurant, reservation: Reservation, item: MenuItem) -> None:
    cart = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
    CartItem.objects.create(
        restaurant=restaurant, cart_session=cart, menu_item=item, quantity=1, guest_slot=1
    )
    confirm_and_pay_preorder(cart_session=cart)


def test_paid_preorder_leaves_session_scheduled_not_open(
    restaurant: Restaurant, table: Table, item: MenuItem
) -> None:
    reservation = _pending_reservation(restaurant, table, start_offset=WEEKS_OUT)

    _pay_preorder(restaurant, reservation, item)

    session = Session.objects.get(reservation=reservation)
    assert session.status == SessionStatus.SCHEDULED
    assert session.orders.filter(payment_status=OrderPaymentStatus.PAID).count() == 1


def test_table_stays_available_tonight_despite_future_preorder(
    restaurant: Restaurant, table: Table, item: MenuItem
) -> None:
    # Not a #69 repro — this passed even with the early OPEN session, because
    # get_session_grace_cutoffs filters reservation__status=ACTIVE, which is
    # exactly why the floor plan kept drawing the table free and staff were
    # blindsided at seating time. Kept as the forward guard: if SCHEDULED is
    # ever folded into the occupancy filters, the far-future booking starts
    # blocking availability and this fails.
    reservation = _pending_reservation(restaurant, table, start_offset=WEEKS_OUT)
    _pay_preorder(restaurant, reservation, item)

    tonight = timezone.now() + timedelta(hours=1)
    unavailable = get_unavailable_table_ids(
        restaurant_id=restaurant.id,
        start_at=tonight,
        end_at=tonight + timedelta(hours=2),
    )

    assert table.id not in unavailable


def test_another_party_can_be_seated_tonight_despite_future_preorder(
    restaurant: Restaurant,
    table: Table,
    restaurant_settings: RestaurantSettings,
    item: MenuItem,
    user_factory: Any,
) -> None:
    actor = user_factory(role=RoleCode.WAITER)
    actor.save()
    future = _pending_reservation(restaurant, table, start_offset=WEEKS_OUT)
    _pay_preorder(restaurant, future, item)

    tonight = _pending_reservation(restaurant, table, start_offset=timedelta(minutes=5))

    seated = activate_pending_reservation(tonight, actor=actor)

    assert seated.status == ReservationStatus.ACTIVE
    assert Session.objects.get(reservation=tonight).status == SessionStatus.OPEN
    assert Session.objects.get(reservation=future).status == SessionStatus.SCHEDULED


def test_plain_checkout_cannot_promote_a_scheduled_session(
    restaurant: Restaurant, table: Table, item: MenuItem
) -> None:
    # create_cart_session doesn't gate on reservation status, so a pre-order
    # cart can reach the plain /checkout/ endpoint. That must not open the
    # table (and fire the kitchen ticket) weeks ahead of the booking.
    reservation = _pending_reservation(restaurant, table, start_offset=WEEKS_OUT)
    _pay_preorder(restaurant, reservation, item)

    second_cart = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
    CartItem.objects.create(
        restaurant=restaurant, cart_session=second_cart, menu_item=item, quantity=1, guest_slot=1
    )

    with (
        patch("apps.orders.billing.is_restaurant_open", return_value=True),
        pytest.raises(ReservationNotYetActiveError),
    ):
        checkout_cart_session(cart_session=second_cart)

    assert Session.objects.get(reservation=reservation).status == SessionStatus.SCHEDULED
    assert not Ticket.objects.filter(session__reservation=reservation).exists()


@pytest.mark.django_db(databases=["default"], transaction=True)
def test_cancelling_preorder_booking_closes_scheduled_session_without_free_event(
    restaurant: Restaurant, table: Table, item: MenuItem, user_factory: Any
) -> None:
    # The session never occupied the table, so reporting occupied->free would
    # push a transition the floor plan never saw begin.
    staff = user_factory(role=RoleCode.WAITER)
    staff.save()
    reservation = _pending_reservation(restaurant, table, start_offset=WEEKS_OUT)
    _pay_preorder(restaurant, reservation, item)

    with (
        patch("apps.reservations.services.emit_hall_table_status_changed") as mock_status,
        patch("apps.reservations.services.emit_hall_reservation_cancelled") as mock_cancelled,
    ):
        cancel_reservation(reservation, actor=staff)

    assert Session.objects.get(reservation=reservation).status == SessionStatus.CLOSED
    mock_status.assert_not_called()
    mock_cancelled.assert_called_once()
