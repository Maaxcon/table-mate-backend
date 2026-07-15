# mypy: disable-error-code="no-untyped-call"
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.reservations.models import Reservation
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


class TestCreateStaffReservation:
    def test_staff_creates_with_guest_name(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        ctx: AuthContext = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
        resp = ctx.client.post(
            _url(),
            {
                "table": str(table.public_id),
                "guest_count": 3,
                "start_at": _future_start(),
                "end_at": _future_end(),
                "guest_name": "John Doe",
                "guest_phone": "+380501234567",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        res = Reservation.objects.get(public_id=resp.data["public_id"])
        assert res.created_by_staff is True
        assert res.customer is None
        assert res.guest_name == "John Doe"
        assert "+380501234567" in res.notes
        assert "John Doe" not in res.notes

    def test_staff_creates_with_notes_formatted(
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
                "guest_name": "Jane Smith",
                "guest_phone": "",
                "notes": "Window seat please",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        res = Reservation.objects.get(public_id=resp.data["public_id"])
        assert res.guest_name == "Jane Smith"
        assert "Window seat please" in res.notes
        assert "Phone" not in res.notes
        assert "Jane Smith" not in res.notes

    def test_customer_cannot_use_guest_name(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        ctx: AuthContext = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        resp = ctx.client.post(
            _url(),
            {
                "table": str(table.public_id),
                "guest_count": 2,
                "start_at": _future_start(),
                "end_at": _future_end(),
                "guest_name": "Sneaky Customer",
            },
            format="json",
        )
        # Customer should still be able to create, but guest_name is ignored
        assert resp.status_code == status.HTTP_201_CREATED
        res = Reservation.objects.get(public_id=resp.data["public_id"])
        assert res.created_by_staff is False
        assert res.customer is not None
