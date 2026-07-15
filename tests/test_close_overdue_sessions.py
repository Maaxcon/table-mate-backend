from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.menu.models import MenuItem
from apps.orders.models import Order, OrderItem, OrderItemStatus, Session, SessionStatus
from apps.orders.services import close_overdue_visit_sessions
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Restaurant, Table, Zone


def _table(restaurant: Restaurant, number: str) -> Table:
    zone, _ = Zone.objects.get_or_create(restaurant=restaurant, defaults={"name": "Main Hall"})
    return Table.objects.create(restaurant=restaurant, public_number=number, capacity=4, zone=zone, active=True)


def _active_reservation(
    restaurant: Restaurant,
    table: Table,
    *,
    end_offset: timedelta,
) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now - timedelta(hours=2),
        end_at=now + end_offset,
        status=ReservationStatus.ACTIVE,
        type=ReservationType.WALK_IN,
    )


@pytest.mark.django_db
def test_closes_session_overdue_beyond_grace(restaurant: Restaurant) -> None:
    reservation = _active_reservation(
        restaurant=restaurant,
        table=_table(restaurant, "S1"),
        end_offset=timedelta(minutes=-25),
    )
    table = reservation.table
    assert table is not None
    session = Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=reservation.guest_count,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=reservation.start_at,
        ends_at=reservation.end_at,
    )

    closed = close_overdue_visit_sessions()

    session.refresh_from_db()
    reservation.refresh_from_db()
    assert closed == 1
    assert session.status == SessionStatus.CLOSED
    assert reservation.status == ReservationStatus.COMPLETED


@pytest.mark.django_db
def test_keeps_session_within_overdue_grace(restaurant: Restaurant) -> None:
    reservation = _active_reservation(
        restaurant=restaurant,
        table=_table(restaurant, "S2"),
        end_offset=timedelta(minutes=-5),
    )
    table = reservation.table
    assert table is not None
    session = Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=reservation.guest_count,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=reservation.start_at,
        ends_at=reservation.end_at,
    )

    closed = close_overdue_visit_sessions()

    session.refresh_from_db()
    reservation.refresh_from_db()
    assert closed == 0
    assert session.status == SessionStatus.OPEN
    assert reservation.status == ReservationStatus.ACTIVE


@pytest.mark.django_db
def test_keeps_auto_extended_session_alive(restaurant: Restaurant) -> None:
    """Session whose ends_at was extended past reservation.end_at survives cleanup."""
    reservation = _active_reservation(
        restaurant=restaurant,
        table=_table(restaurant, "S3"),
        end_offset=timedelta(minutes=-25),
    )
    table = reservation.table
    assert table is not None
    Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=reservation.guest_count,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=reservation.start_at,
        ends_at=timezone.now() + timedelta(minutes=10),
    )

    closed = close_overdue_visit_sessions()

    session = Session.objects.get(reservation=reservation)
    assert closed == 0
    assert session.status == SessionStatus.OPEN


@pytest.mark.django_db
def test_skips_unclosable_session_and_keeps_processing_later_rows(
    restaurant: Restaurant,
    item: MenuItem,
) -> None:
    poison_reservation = _active_reservation(
        restaurant=restaurant,
        table=_table(restaurant, "S4"),
        end_offset=timedelta(minutes=-25),
    )
    poison_table = poison_reservation.table
    assert poison_table is not None
    poison_session = Session.objects.create(
        restaurant=restaurant,
        table=poison_table,
        reservation=poison_reservation,
        guest_count=poison_reservation.guest_count,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=poison_reservation.start_at,
        ends_at=poison_reservation.end_at,
    )
    poison_order = Order.objects.create(
        restaurant=restaurant,
        session=poison_session,
        currency="UAH",
    )
    OrderItem.objects.create(
        restaurant=restaurant,
        order=poison_order,
        menu_item=item,
        guest_slot=1,
        quantity=1,
        status=OrderItemStatus.PENDING,
        unit_price=Decimal("29.9900"),
        total_price=Decimal("29.9900"),
    )

    clean_reservation = _active_reservation(
        restaurant=restaurant,
        table=_table(restaurant, "S5"),
        end_offset=timedelta(minutes=-25),
    )
    clean_table = clean_reservation.table
    assert clean_table is not None
    clean_session = Session.objects.create(
        restaurant=restaurant,
        table=clean_table,
        reservation=clean_reservation,
        guest_count=clean_reservation.guest_count,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=clean_reservation.start_at,
        ends_at=clean_reservation.end_at,
    )

    closed = close_overdue_visit_sessions(batch_size=1)

    poison_session.refresh_from_db()
    clean_session.refresh_from_db()
    poison_reservation.refresh_from_db()
    clean_reservation.refresh_from_db()
    assert closed == 1
    assert poison_session.status == SessionStatus.OPEN
    assert poison_reservation.status == ReservationStatus.ACTIVE
    assert clean_session.status == SessionStatus.CLOSED
    assert clean_reservation.status == ReservationStatus.COMPLETED
