from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.menu.models import MenuItem
from apps.orders.models import Order, OrderItem, OrderItemStatus, Session, SessionStatus
from apps.orders.services import force_close_sessions_past_shift_end
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Restaurant, RestaurantSettings, Table, Zone

# Wednesday: open 09:00, close 22:00 UTC.
WORKING_HOURS = {
    "mon": {"open": "09:00", "close": "22:00"},
    "tue": {"open": "09:00", "close": "22:00"},
    "wed": {"open": "09:00", "close": "22:00"},
    "thu": {"open": "09:00", "close": "22:00"},
    "fri": {"open": "09:00", "close": "22:00"},
    "sat": {"open": "09:00", "close": "22:00"},
    "sun": {"open": "09:00", "close": "22:00"},
}
WED_CLOSE_UTC = datetime(2026, 6, 17, 22, 0, tzinfo=ZoneInfo("UTC"))


def _settings(restaurant: Restaurant) -> RestaurantSettings:
    obj, _ = RestaurantSettings.objects.update_or_create(
        restaurant=restaurant,
        defaults={"currency": "UAH", "timezone": "UTC", "working_hours": WORKING_HOURS},
    )
    return obj


def _table(restaurant: Restaurant, number: str) -> Table:
    zone, _ = Zone.objects.get_or_create(restaurant=restaurant, defaults={"name": "Main Hall"})
    return Table.objects.create(restaurant=restaurant, public_number=number, capacity=4, zone=zone, active=True)


def _stuck_session(
    restaurant: Restaurant, table: Table, item: MenuItem | None = None
) -> tuple[Reservation, Session]:
    """An ACTIVE reservation with an OPEN session that still has an unserved item —
    the kind close_overdue_visit_sessions refuses to close on its own."""
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=WED_CLOSE_UTC - timedelta(hours=3),
        end_at=WED_CLOSE_UTC - timedelta(hours=1),
        status=ReservationStatus.ACTIVE,
        type=ReservationType.WALK_IN,
    )
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
    if item is not None:
        order = Order.objects.create(restaurant=restaurant, session=session, currency="UAH")
        OrderItem.objects.create(
            restaurant=restaurant,
            order=order,
            menu_item=item,
            guest_slot=1,
            quantity=1,
            status=OrderItemStatus.READY,
            unit_price=Decimal("29.9900"),
            total_price=Decimal("29.9900"),
        )
    return reservation, session


@pytest.mark.django_db
def test_force_closes_stuck_session_past_grace(restaurant: Restaurant, item: MenuItem) -> None:
    _settings(restaurant)
    reservation, session = _stuck_session(restaurant, _table(restaurant, "F1"), item)

    closed = force_close_sessions_past_shift_end(now=WED_CLOSE_UTC + timedelta(minutes=61))

    session.refresh_from_db()
    reservation.refresh_from_db()
    assert closed == 1
    assert session.status == SessionStatus.CLOSED
    assert reservation.status == ReservationStatus.COMPLETED


@pytest.mark.django_db
def test_keeps_session_within_shift_end_grace(restaurant: Restaurant, item: MenuItem) -> None:
    _settings(restaurant)
    reservation, session = _stuck_session(restaurant, _table(restaurant, "F2"), item)

    closed = force_close_sessions_past_shift_end(now=WED_CLOSE_UTC + timedelta(minutes=30))

    session.refresh_from_db()
    reservation.refresh_from_db()
    assert closed == 0
    assert session.status == SessionStatus.OPEN
    assert reservation.status == ReservationStatus.ACTIVE


@pytest.mark.django_db
def test_skips_restaurant_without_working_hours(restaurant: Restaurant, item: MenuItem) -> None:
    # No RestaurantSettings row at all → no shift boundary to force-close against.
    reservation, session = _stuck_session(restaurant, _table(restaurant, "F3"), item)

    closed = force_close_sessions_past_shift_end(now=WED_CLOSE_UTC + timedelta(days=1))

    session.refresh_from_db()
    reservation.refresh_from_db()
    assert closed == 0
    assert session.status == SessionStatus.OPEN
    assert reservation.status == ReservationStatus.ACTIVE


@pytest.mark.django_db
def test_does_not_touch_other_restaurants(restaurant: Restaurant, empty_restaurant: Restaurant, item: MenuItem) -> None:
    _settings(restaurant)
    # empty_restaurant has no settings/working hours, so its session must survive
    # regardless of items — no shift boundary means the grace check never fires.
    _, other_session = _stuck_session(empty_restaurant, _table(empty_restaurant, "F4"))
    reservation, session = _stuck_session(restaurant, _table(restaurant, "F5"), item)

    closed = force_close_sessions_past_shift_end(now=WED_CLOSE_UTC + timedelta(minutes=61))

    session.refresh_from_db()
    other_session.refresh_from_db()
    assert closed == 1
    assert session.status == SessionStatus.CLOSED
    assert other_session.status == SessionStatus.OPEN


@pytest.mark.django_db
def test_timezone_utils_now_default_used_when_not_provided(restaurant: Restaurant, item: MenuItem) -> None:
    # Sanity check that omitting `now` doesn't crash and simply uses the real
    # clock (this restaurant has no settings, so nothing gets closed).
    reservation, session = _stuck_session(restaurant, _table(restaurant, "F6"), item)

    closed = force_close_sessions_past_shift_end()

    session.refresh_from_db()
    assert closed == 0
    assert session.status == SessionStatus.OPEN
    assert timezone.now() is not None
