# mypy: disable-error-code="no-untyped-call"
from datetime import datetime, timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework import status

from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import Restaurant, RestaurantSettings, Table

pytestmark = pytest.mark.django_db


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
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

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
