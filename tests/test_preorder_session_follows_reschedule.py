"""A rescheduled booking must drag its paid pre-order's Session along with it.

Follow-up to unibrix/table-mate-backend#69. The SCHEDULED session fixing that
issue now lives on a PENDING reservation for as long as the booking is out —
weeks — and both reschedule paths (reschedule_reservation and
batch_update_reservations) only rewrite the Session of an ACTIVE reservation.
So a booking moved after its pre-order was paid used to keep a Session pointing
at the old table and the old end time, and ensure_visit_session promoted those
stale values verbatim when the party was finally seated.
"""

from datetime import datetime, timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.authentication.models import RoleCode
from apps.menu.models import MenuItem
from apps.orders.billing import confirm_and_pay_preorder
from apps.orders.models import CartItem, CartSession, Session, SessionStatus
from apps.orders.services.sessions import close_overdue_visit_sessions
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.reservations.services import (
    activate_pending_reservation,
    batch_update_reservations,
    reschedule_reservation,
)
from apps.restaurants.models import Restaurant, Table, Zone

pytestmark = pytest.mark.django_db

WEEKS_OUT = timedelta(weeks=3)


def _pending_reservation(
    restaurant: Restaurant, table: Table, *, start_offset: timedelta
) -> Reservation:
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


def _pay_preorder(restaurant: Restaurant, reservation: Reservation, item: MenuItem) -> None:
    cart = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
    CartItem.objects.create(
        restaurant=restaurant, cart_session=cart, menu_item=item, quantity=1, guest_slot=1
    )
    confirm_and_pay_preorder(cart_session=cart)


@pytest.fixture
def other_table(restaurant: Restaurant, zone: Zone) -> Table:
    return Table.objects.create(
        restaurant=restaurant,
        public_number="T2",
        capacity=4,
        zone=zone,
        active=True,
    )


def test_moving_a_paid_booking_to_another_table_moves_its_scheduled_session(
    restaurant: Restaurant, table: Table, other_table: Table, item: MenuItem, user_factory: Any
) -> None:
    actor = user_factory(role=RoleCode.WAITER)
    actor.save()
    reservation = _pending_reservation(restaurant, table, start_offset=WEEKS_OUT)
    _pay_preorder(restaurant, reservation, item)

    reschedule_reservation(
        reservation,
        {
            "table": other_table,
            "start_at": timezone.now() + timedelta(minutes=5),
            "end_at": timezone.now() + timedelta(hours=1, minutes=5),
        },
    )
    reservation.refresh_from_db()
    activate_pending_reservation(reservation, actor=actor)

    session = Session.objects.get(reservation=reservation)
    assert session.status == SessionStatus.OPEN
    assert session.table_id == other_table.id


def test_seating_a_postponed_booking_is_not_immediately_swept_as_overdue(
    restaurant: Restaurant, table: Table, item: MenuItem, user_factory: Any
) -> None:
    # The original end_at is long past by the time the party sits down, so a
    # session promoted with that stale ends_at is overdue the moment it opens.
    actor = user_factory(role=RoleCode.WAITER)
    actor.save()
    reservation = _pending_reservation(restaurant, table, start_offset=-WEEKS_OUT)
    _pay_preorder(restaurant, reservation, item)

    reschedule_reservation(
        reservation,
        {
            "start_at": timezone.now() + timedelta(minutes=5),
            "end_at": timezone.now() + timedelta(hours=1, minutes=5),
        },
    )
    reservation.refresh_from_db()
    activate_pending_reservation(reservation, actor=actor)

    assert close_overdue_visit_sessions() == 0
    session = Session.objects.get(reservation=reservation)
    assert session.status == SessionStatus.OPEN
    assert session.ends_at == reservation.end_at


def test_batch_moving_a_paid_booking_moves_its_scheduled_session(
    restaurant: Restaurant, table: Table, other_table: Table, item: MenuItem, user_factory: Any
) -> None:
    # Staff drag-and-drop on the bookings board goes through batch_update, not
    # the single-reservation PATCH.
    actor = user_factory(role=RoleCode.WAITER)
    actor.save()
    reservation = _pending_reservation(restaurant, table, start_offset=WEEKS_OUT)
    _pay_preorder(restaurant, reservation, item)

    soon: datetime = timezone.localtime(timezone.now() + timedelta(minutes=5))
    batch_update_reservations(
        restaurant_id=restaurant.id,
        changes=[
            {
                "reservation_id": str(reservation.public_id),
                "new_table_id": str(other_table.public_id),
                "new_date": soon.date(),
                "new_start_time": soon.time().replace(second=0, microsecond=0),
                "new_end_time": (soon + timedelta(hours=1)).time().replace(second=0, microsecond=0),
            }
        ],
        actor=actor,
    )
    reservation.refresh_from_db()
    activate_pending_reservation(reservation, actor=actor)

    session = Session.objects.get(reservation=reservation)
    assert session.status == SessionStatus.OPEN
    assert session.table_id == other_table.id
    assert session.ends_at == reservation.end_at
