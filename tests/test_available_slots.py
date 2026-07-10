# mypy: disable-error-code="no-untyped-call"
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from rest_framework import status

from apps.orders.models import Session, SessionStatus
from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import Restaurant, RestaurantSettings, Table
from apps.restaurants.selectors import _DAY_KEYS

KYIV = ZoneInfo("Europe/Kyiv")
UTC = ZoneInfo("UTC")

pytestmark = pytest.mark.django_db

AVAILABLE_SLOTS_URL = "/api/reservations/reservations/available-slots/"
AVAILABILITY_URL = "/api/reservations/reservations/availability/"


def _reservation(
    *,
    restaurant: Restaurant,
    table: Table,
    start_offset_hours: int = 2,
) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now + timedelta(hours=start_offset_hours),
        end_at=now + timedelta(hours=start_offset_hours + 1),
        status=ReservationStatus.PENDING,
    )


def _url(table_id: str, date_str: str | None = None) -> str:
    base = f"/api/reservations/reservations/available-slots/?table={table_id}"
    if date_str:
        base += f"&date={date_str}"
    return base


class TestAvailableSlots:
    def test_returns_slots_for_valid_day(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        tomorrow = (timezone.now() + timedelta(days=1)).date()
        client = api().client  # unauthenticated (AllowAny)
        resp = client.get(_url(str(table.public_id), tomorrow.isoformat()))
        assert resp.status_code == status.HTTP_200_OK
        data = resp.data
        assert isinstance(data, dict)
        assert tomorrow.isoformat() in data
        slots = data[tomorrow.isoformat()]
        assert isinstance(slots, list)
        assert len(slots) > 0

    def test_past_date_rejected(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        yesterday = (timezone.now() - timedelta(days=1)).date()
        client = api().client
        resp = client.get(_url(str(table.public_id), yesterday.isoformat()))
        assert resp.status_code == status.HTTP_200_OK

    def test_missing_table_param_rejected(
        self, api: Any, restaurant: Restaurant, restaurant_settings: RestaurantSettings
    ) -> None:
        client = api().client
        resp = client.get("/api/reservations/reservations/available-slots/")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_nonexistent_table_rejected(
        self, api: Any, restaurant: Restaurant, restaurant_settings: RestaurantSettings
    ) -> None:
        client = api().client
        resp = client.get(_url("00000000-0000-0000-0000-000000000000"))
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_excludes_occupied_slots(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        from zoneinfo import ZoneInfo

        tomorrow = (timezone.now() + timedelta(days=1)).date()
        tz = ZoneInfo("Europe/Kyiv")
        # Create a reservation at 10:00 local time (which is 07:00 UTC for Kyiv)
        res_start_local = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 10, 0, tzinfo=tz)
        res_end_local = res_start_local + timedelta(hours=1)
        Reservation.objects.create(
            restaurant=restaurant,
            table=table,
            guest_count=2,
            start_at=res_start_local.astimezone(ZoneInfo("UTC")),
            end_at=res_end_local.astimezone(ZoneInfo("UTC")),
            status=ReservationStatus.PENDING,
        )

        client = api().client
        resp = client.get(_url(str(table.public_id), tomorrow.isoformat()))
        assert resp.status_code == status.HTTP_200_OK
        slots = resp.data[tomorrow.isoformat()]
        # The 10:00 and 10:30 slots should be excluded
        assert "10:00" not in slots
        assert "10:30" not in slots

    def test_exclude_ids_parameter(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        from zoneinfo import ZoneInfo

        tomorrow = (timezone.now() + timedelta(days=1)).date()
        tz = ZoneInfo("Europe/Kyiv")
        res_start_local = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 10, 0, tzinfo=tz)
        res_end_local = res_start_local + timedelta(hours=1)
        res = Reservation.objects.create(
            restaurant=restaurant,
            table=table,
            guest_count=2,
            start_at=res_start_local.astimezone(ZoneInfo("UTC")),
            end_at=res_end_local.astimezone(ZoneInfo("UTC")),
            status=ReservationStatus.PENDING,
        )

        client = api().client
        # Without exclude, slots should be occupied
        resp = client.get(_url(str(table.public_id), tomorrow.isoformat()))
        assert "10:00" not in resp.data[tomorrow.isoformat()]

        # With exclude, slots should be available
        resp2 = client.get(
            f"{_url(str(table.public_id), tomorrow.isoformat())}&exclude={res.public_id}"
        )
        assert "10:00" in resp2.data[tomorrow.isoformat()]


@pytest.mark.django_db
def test_available_slots_excludes_own_session_from_grace_cutoff(
    restaurant: Restaurant,
    table: Table,
    restaurant_settings: RestaurantSettings,
    user_factory: Callable[..., Any],
    api_client: Any,
) -> None:
    customer = user_factory()
    customer.save()

    today_kyiv = datetime.now(KYIV).date()
    fixed_now = datetime(today_kyiv.year, today_kyiv.month, today_kyiv.day, 12, 5, tzinfo=KYIV).astimezone(UTC)

    reservation = Reservation.objects.create(
        restaurant=restaurant,
        customer=customer,
        table=table,
        guest_count=2,
        start_at=fixed_now - timedelta(hours=2),
        end_at=fixed_now - timedelta(hours=1),
        status=ReservationStatus.ACTIVE,
    )
    Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=2,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=reservation.start_at,
    )

    with patch("apps.reservations.views.timezone.now", return_value=fixed_now):
        resp = api_client.get(
            AVAILABLE_SLOTS_URL,
            {
                "table": str(table.public_id),
                "date": today_kyiv.isoformat(),
                "exclude": str(reservation.public_id),
            },
        )

    assert resp.status_code == 200
    slots = resp.json()[today_kyiv.isoformat()]
    assert "12:30" in slots


@pytest.mark.django_db
def test_available_slots_without_exclude_still_blocks_others_sessions(
    restaurant: Restaurant,
    table: Table,
    restaurant_settings: RestaurantSettings,
    user_factory: Callable[..., Any],
    api_client: Any,
) -> None:
    customer = user_factory()
    customer.save()

    today_kyiv = datetime.now(KYIV).date()
    fixed_now = datetime(today_kyiv.year, today_kyiv.month, today_kyiv.day, 12, 5, tzinfo=KYIV).astimezone(UTC)

    reservation = Reservation.objects.create(
        restaurant=restaurant,
        customer=customer,
        table=table,
        guest_count=2,
        start_at=fixed_now - timedelta(hours=2),
        end_at=fixed_now - timedelta(hours=1),
        status=ReservationStatus.ACTIVE,
    )
    Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=2,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=reservation.start_at,
    )

    with patch("apps.reservations.views.timezone.now", return_value=fixed_now):
        resp = api_client.get(
            AVAILABLE_SLOTS_URL,
            {"table": str(table.public_id), "date": today_kyiv.isoformat()},
        )

    assert resp.status_code == 200
    slots = resp.json()[today_kyiv.isoformat()]
    assert "12:30" not in slots


@pytest.mark.django_db
def test_available_slots_and_availability_agree_at_a_misaligned_closing_tail(
    restaurant: Restaurant,
    table: Table,
    restaurant_settings: RestaurantSettings,
    api_client: Any,
) -> None:
    target_date = (datetime.now(KYIV) + timedelta(days=7)).date()
    day_key = _DAY_KEYS[target_date.weekday()]
    restaurant_settings.working_hours = {
        **restaurant_settings.working_hours,
        day_key: {"open": "10:00", "close": "22:40"},
    }
    restaurant_settings.save(update_fields=["working_hours"])

    slots_resp = api_client.get(
        AVAILABLE_SLOTS_URL,
        {"table": str(table.public_id), "date": target_date.isoformat()},
    )
    assert slots_resp.status_code == 200
    slots = slots_resp.json()[target_date.isoformat()]

    assert "22:00" in slots
    assert "22:30" not in slots

    avail_resp = api_client.get(
        AVAILABILITY_URL,
        {
            "restaurant": str(restaurant.public_id),
            "date": target_date.isoformat(),
            "time": "22:30",
            "duration": 30,
        },
    )
    assert avail_resp.status_code == 200
    assert avail_resp.json()["availability"][str(table.public_id)] is False

    avail_resp_ok = api_client.get(
        AVAILABILITY_URL,
        {
            "restaurant": str(restaurant.public_id),
            "date": target_date.isoformat(),
            "time": "22:00",
            "duration": 30,
        },
    )
    assert avail_resp_ok.status_code == 200
    assert avail_resp_ok.json()["availability"][str(table.public_id)] is True


@pytest.mark.django_db
def test_available_slots_filters_past_slots_on_an_explicitly_queried_past_date(
    restaurant: Restaurant,
    table: Table,
    restaurant_settings: RestaurantSettings,
    api_client: Any,
) -> None:
    today_kyiv = datetime.now(KYIV).date()
    yesterday = today_kyiv - timedelta(days=1)
    day_key = _DAY_KEYS[yesterday.weekday()]
    restaurant_settings.working_hours = {
        **restaurant_settings.working_hours,
        day_key: {"open": "10:00", "close": "20:00"},
    }
    restaurant_settings.save(update_fields=["working_hours"])
    fixed_now = datetime(today_kyiv.year, today_kyiv.month, today_kyiv.day, 8, 0, tzinfo=KYIV).astimezone(UTC)

    with patch("apps.reservations.views.timezone.now", return_value=fixed_now):
        resp = api_client.get(
            AVAILABLE_SLOTS_URL,
            {"table": str(table.public_id), "date": yesterday.isoformat()},
        )

    assert resp.status_code == 200
    assert resp.json()[yesterday.isoformat()] == []
