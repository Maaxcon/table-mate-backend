from datetime import datetime, timedelta
from typing import Any
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.orders.services import add_item_to_cart, ensure_active_cart_for_table
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Restaurant, RestaurantSettings, Table
from apps.restaurants.selectors import _DAY_KEYS, is_restaurant_open
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

    with mock.patch("apps.orders.services.is_restaurant_open", return_value=False):
        with pytest.raises(RestaurantClosedError):
            add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=1)

    assert cart.items.count() == 0


@pytest.mark.django_db
def test_add_item_allowed_when_restaurant_open(restaurant: Restaurant, table: Table, item: Any) -> None:
    _active_reservation(restaurant, table)
    cart = ensure_active_cart_for_table(table=table)

    with mock.patch("apps.orders.services.is_restaurant_open", return_value=True):
        cart_item = add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=1)

    assert cart_item.quantity == 1
