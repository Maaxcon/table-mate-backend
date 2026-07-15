# mypy: disable-error-code="no-untyped-call"
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.reservations.models import ReservationStatus
from apps.restaurants.models import Restaurant, RestaurantSettings, Table

from .conftest import AuthContext

pytestmark = pytest.mark.django_db


def _future_start(hours: int = 2) -> str:
    dt = timezone.now() + timedelta(hours=hours)
    return dt.isoformat()


def _future_end(hours: int = 3) -> str:
    dt = timezone.now() + timedelta(hours=hours)
    return dt.isoformat()


def _url() -> str:
    return "/api/reservations/reservations/"


class TestCreateReservationValidation:
    def test_guest_count_zero_rejected(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        resp = ctx.client.post(
            _url(),
            {
                "table": str(table.public_id),
                "guest_count": 0,
                "start_at": _future_start(),
                "end_at": _future_end(),
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "at least 1" in str(resp.data).lower() or "guest_count" in str(resp.data).lower()

    def test_start_at_in_past_rejected(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        past = (timezone.now() - timedelta(hours=1)).isoformat()
        resp = ctx.client.post(
            _url(),
            {
                "table": str(table.public_id),
                "guest_count": 2,
                "start_at": past,
                "end_at": _future_end(),
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "future" in str(resp.data).lower() or "start_at" in str(resp.data).lower()

    def test_duration_exceeds_max_rejected(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        resp = ctx.client.post(
            _url(),
            {
                "table": str(table.public_id),
                "guest_count": 2,
                "start_at": _future_start(2),
                "end_at": _future_end(2 + 9),  # 9 hours > 8 hour max
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_notes_exceed_max_length_rejected(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        resp = ctx.client.post(
            _url(),
            {
                "table": str(table.public_id),
                "guest_count": 2,
                "start_at": _future_start(),
                "end_at": _future_end(),
                "notes": "x" * 2001,
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_guest_count_exceeds_capacity_rejected_for_customer(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings, user_factory: Any
    ) -> None:
        customer = user_factory()
        customer.save()
        ctx: AuthContext = api(role=RoleCode.CUSTOMER)
        ctx.client.force_authenticate(user=customer)
        resp = ctx.client.post(
            _url(),
            {
                "table": str(table.public_id),
                "guest_count": 999,
                "start_at": _future_start(),
                "end_at": _future_end(),
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "capacity" in str(resp.data).lower()

    def test_staff_can_exceed_capacity(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        resp = ctx.client.post(
            _url(),
            {
                "table": str(table.public_id),
                "guest_count": 999,
                "start_at": _future_start(),
                "end_at": _future_end(),
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED

    def test_invalid_table_rejected(
        self, api: Any, restaurant: Restaurant, restaurant_settings: RestaurantSettings
    ) -> None:
        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        resp = ctx.client.post(
            _url(),
            {
                "table": "00000000-0000-0000-0000-000000000000",
                "guest_count": 2,
                "start_at": _future_start(),
                "end_at": _future_end(),
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_happy_path_creates_reservation(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        resp = ctx.client.post(
            _url(),
            {
                "table": str(table.public_id),
                "guest_count": 2,
                "start_at": _future_start(),
                "end_at": _future_end(),
                "notes": "Test note",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["status"] == ReservationStatus.PENDING
        assert resp.data["guest_count"] == 2

    def test_outside_operating_hours_rejected(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        # Try to create a reservation at 3 AM (outside 09:00-22:00)
        now = timezone.now()
        tomorrow = now + timedelta(days=1)
        start = tomorrow.replace(hour=3, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1)
        resp = ctx.client.post(
            _url(),
            {
                "table": str(table.public_id),
                "guest_count": 2,
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_409_CONFLICT
