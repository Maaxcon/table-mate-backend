from datetime import datetime, timedelta
from typing import Any
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.orders.services import add_item_to_cart, ensure_active_cart_for_table
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.management.commands.seed_restaurants import DEFAULT_WORKING_HOURS
from apps.restaurants.models import Restaurant, RestaurantSettings, Table, validate_working_hours
from apps.restaurants.selectors import _DAY_KEYS, get_working_hours_close_at, is_restaurant_open
from common.exceptions import RestaurantClosedError

ALL_DAYS = {d: {"open": "09:00", "close": "22:00"} for d in _DAY_KEYS}
# A fixed Wednesday 13:00 UTC reference for the time-of-day checks.
WED_1300_UTC = datetime(2026, 6, 17, 13, 0, tzinfo=ZoneInfo("UTC"))


def _settings(restaurant: Restaurant, working_hours: dict[str, Any], tz: str = "UTC") -> RestaurantSettings:
    obj, _ = RestaurantSettings.objects.update_or_create(
        restaurant=restaurant,
        defaults={"currency": "USD", "timezone": tz, "working_hours": working_hours},
    )
    return obj


def test_seed_default_working_hours_use_canonical_keys() -> None:
    # Seeded hours must use the same keys the selector and validator expect,
    # otherwise every seeded restaurant reads as closed.
    assert set(DEFAULT_WORKING_HOURS) == set(_DAY_KEYS)
    validate_working_hours(DEFAULT_WORKING_HOURS)


@pytest.mark.django_db
def test_open_within_window(restaurant: Restaurant) -> None:
    _settings(restaurant, ALL_DAYS)
    assert is_restaurant_open(restaurant.id, when=WED_1300_UTC) is True


@pytest.mark.django_db
def test_closed_before_open_and_after_close(restaurant: Restaurant) -> None:
    _settings(restaurant, ALL_DAYS)
    assert is_restaurant_open(restaurant.id, when=WED_1300_UTC.replace(hour=8)) is False
    assert is_restaurant_open(restaurant.id, when=WED_1300_UTC.replace(hour=23)) is False


@pytest.mark.django_db
def test_open_minute_is_inclusive(restaurant: Restaurant) -> None:
    # ALL_DAYS opens at 09:00; the open minute itself counts as open.
    _settings(restaurant, ALL_DAYS)
    assert is_restaurant_open(restaurant.id, when=WED_1300_UTC.replace(hour=9, minute=0)) is True


@pytest.mark.django_db
def test_close_minute_is_exclusive(restaurant: Restaurant) -> None:
    # ALL_DAYS closes at 22:00; now_min == close_min must read as closed
    # (the window is [open, close), excluded by '< close_min').
    _settings(restaurant, ALL_DAYS)
    assert is_restaurant_open(restaurant.id, when=WED_1300_UTC.replace(hour=22, minute=0)) is False
    # One minute before close is still open.
    assert is_restaurant_open(restaurant.id, when=WED_1300_UTC.replace(hour=21, minute=59)) is True


@pytest.mark.django_db
def test_closed_when_day_has_no_hours(restaurant: Restaurant) -> None:
    other_day = next(d for d in _DAY_KEYS if d != _DAY_KEYS[WED_1300_UTC.weekday()])
    _settings(restaurant, {other_day: {"open": "09:00", "close": "22:00"}})
    assert is_restaurant_open(restaurant.id, when=WED_1300_UTC) is False


@pytest.mark.django_db
def test_closed_when_day_hours_are_malformed(restaurant: Restaurant) -> None:
    # Day is configured but its times can't be parsed → treated as closed,
    # same as a day with no entry (config is authoritative once set).
    today = _DAY_KEYS[WED_1300_UTC.weekday()]
    _settings(restaurant, {today: {"open": "9am", "close": "22:00"}})
    assert is_restaurant_open(restaurant.id, when=WED_1300_UTC) is False


@pytest.mark.django_db
def test_no_settings_or_no_hours_treated_as_open(restaurant: Restaurant, empty_restaurant: Restaurant) -> None:
    # restaurant with no settings row at all
    assert is_restaurant_open(empty_restaurant.id, when=WED_1300_UTC) is True
    # settings with empty working_hours
    _settings(restaurant, {})
    assert is_restaurant_open(restaurant.id, when=WED_1300_UTC) is True


@pytest.mark.django_db
def test_overnight_window(restaurant: Restaurant) -> None:
    _settings(restaurant, {d: {"open": "22:00", "close": "02:00"} for d in _DAY_KEYS})
    assert is_restaurant_open(restaurant.id, when=WED_1300_UTC.replace(hour=23)) is True
    assert is_restaurant_open(restaurant.id, when=WED_1300_UTC.replace(hour=1)) is True
    assert is_restaurant_open(restaurant.id, when=WED_1300_UTC.replace(hour=12)) is False


@pytest.mark.django_db
def test_working_hours_close_at_uses_previous_day_overnight_tail_when_today_is_different(
    restaurant: Restaurant,
) -> None:
    tz = ZoneInfo("Europe/Kyiv")
    _settings(
        restaurant,
        {
            "mon": {"open": "18:00", "close": "02:00"},
            "tue": {"open": "09:00", "close": "22:00"},
        },
        tz="Europe/Kyiv",
    )

    when = datetime(2026, 6, 16, 1, 20, tzinfo=tz)
    close_at = get_working_hours_close_at(restaurant.id, when)

    assert close_at is not None
    assert close_at.astimezone(tz) == datetime(2026, 6, 16, 2, 0, tzinfo=tz)


@pytest.mark.django_db
def test_working_hours_close_at_uses_previous_day_overnight_tail_when_today_is_closed(
    restaurant: Restaurant,
) -> None:
    tz = ZoneInfo("Europe/Kyiv")
    _settings(
        restaurant,
        {
            "mon": {"open": "18:00", "close": "02:00"},
        },
        tz="Europe/Kyiv",
    )

    when = datetime(2026, 6, 16, 1, 20, tzinfo=tz)
    close_at = get_working_hours_close_at(restaurant.id, when)

    assert close_at is not None
    assert close_at.astimezone(tz) == datetime(2026, 6, 16, 2, 0, tzinfo=tz)


@pytest.mark.django_db
def test_respects_timezone(restaurant: Restaurant) -> None:
    # 13:00 UTC == 16:00 Kyiv; window 15:00-17:00 local → open.
    _settings(restaurant, {d: {"open": "15:00", "close": "17:00"} for d in _DAY_KEYS}, tz="Europe/Kyiv")
    assert is_restaurant_open(restaurant.id, when=WED_1300_UTC) is True


def _active_reservation(restaurant: Restaurant, table: Table) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now - timedelta(minutes=10),
        end_at=now + timedelta(hours=2),
        status=ReservationStatus.ACTIVE,
        type=ReservationType.PRE_BOOKED,
    )


@pytest.mark.django_db
def test_add_item_blocked_when_restaurant_closed(restaurant: Restaurant, table: Table, item: Any) -> None:
    _active_reservation(restaurant, table)
    cart = ensure_active_cart_for_table(table=table)

    with mock.patch("apps.orders.services.cart.is_restaurant_open", return_value=False):
        with pytest.raises(RestaurantClosedError):
            add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=1)

    assert cart.items.count() == 0


@pytest.mark.django_db
def test_add_item_allowed_when_restaurant_open(restaurant: Restaurant, table: Table, item: Any) -> None:
    _active_reservation(restaurant, table)
    cart = ensure_active_cart_for_table(table=table)

    with mock.patch("apps.orders.services.cart.is_restaurant_open", return_value=True):
        cart_item = add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=1)

    assert cart_item.quantity == 1
