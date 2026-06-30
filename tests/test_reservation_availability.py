from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import Restaurant, RestaurantSettings, Table

KYIV = ZoneInfo("Europe/Kyiv")
UTC = ZoneInfo("UTC")

AVAILABILITY_URL = "/api/reservations/reservations/availability/"


def _future_slot(days_ahead: int = 7, hour: int = 12) -> tuple[Any, datetime, datetime]:
    """A slot guaranteed to be in the future and inside 09:00–22:00 working hours."""
    slot_date = (timezone.now().astimezone(KYIV) + timedelta(days=days_ahead)).date()
    start = datetime(slot_date.year, slot_date.month, slot_date.day, hour, 0, tzinfo=KYIV).astimezone(UTC)
    return slot_date, start, start + timedelta(minutes=120)


@pytest.mark.django_db
def test_availability_marks_overlapping_table_unavailable(
    restaurant: Restaurant,
    table: Table,
    restaurant_settings: RestaurantSettings,
    user_factory: Callable[..., Any],
    api_client: Any,
) -> None:
    customer = user_factory()
    customer.save()
    free_table = Table.objects.create(
        restaurant=restaurant, table_number="T2", capacity=2, active=True
    )

    slot_date, start, end = _future_slot()
    Reservation.objects.create(
        restaurant=restaurant,
        customer=customer,
        table=table,
        guest_count=2,
        start_at=start,
        end_at=end,
        status=ReservationStatus.PENDING,
    )

    resp = api_client.get(
        AVAILABILITY_URL,
        {
            "restaurant": str(restaurant.public_id),
            "date": slot_date.isoformat(),
            "time": "12:00",
            "duration": 120,
        },
    )

    assert resp.status_code == 200
    avail = resp.json()["availability"]
    assert avail[str(table.public_id)] is False
    assert avail[str(free_table.public_id)] is True


@pytest.mark.django_db
def test_availability_all_false_for_past_slot(
    restaurant: Restaurant,
    table: Table,
    restaurant_settings: RestaurantSettings,
    api_client: Any,
) -> None:
    yesterday = (timezone.now().astimezone(KYIV) - timedelta(days=1)).date()

    resp = api_client.get(
        AVAILABILITY_URL,
        {"restaurant": str(restaurant.public_id), "date": yesterday.isoformat(), "time": "12:00"},
    )

    assert resp.status_code == 200
    avail = resp.json()["availability"]
    assert avail[str(table.public_id)] is False


@pytest.mark.django_db
def test_availability_false_outside_working_hours(
    restaurant: Restaurant,
    table: Table,
    restaurant_settings: RestaurantSettings,
    api_client: Any,
) -> None:
    slot_date, _, _ = _future_slot()

    resp = api_client.get(
        AVAILABILITY_URL,
        {"restaurant": str(restaurant.public_id), "date": slot_date.isoformat(), "time": "07:00"},
    )

    assert resp.status_code == 200
    assert resp.json()["availability"][str(table.public_id)] is False


@pytest.mark.django_db
def test_availability_requires_date_and_time(
    restaurant: Restaurant,
    table: Table,
    api_client: Any,
) -> None:
    resp = api_client.get(AVAILABILITY_URL, {"restaurant": str(restaurant.public_id)})
    assert resp.status_code == 400
