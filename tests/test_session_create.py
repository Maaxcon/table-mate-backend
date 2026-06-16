# mypy: disable-error-code="no-untyped-call"
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from django.urls import reverse
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.orders.models import Session, SessionStatus
from apps.restaurants.models import Table

from .conftest import AuthContext

URL = reverse("session-list")


@pytest.mark.django_db(databases=["default"])
class TestSessionCreate:
    def test_waiter_can_create_walk_in_session(
        self,
        api: Callable[..., AuthContext],
        table: Table,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        response = auth.client.post(
            URL,
            {
                "table": str(table.public_id),
                "guest_count": 2,
                "opened_at": datetime.now(UTC).isoformat(),
                "currency": "UAH",
            },
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["table"] == str(table.public_id)
        assert data["status"] == "open"
        assert data["reservation"] is not None

        session = Session.objects.get(public_id=data["public_id"])
        assert session.status == SessionStatus.OPEN
        assert session.reservation is not None
        assert session.reservation.status == "active"
        assert session.reservation.type == "walk_in"

    def test_returns_409_when_table_already_has_open_session(
        self,
        api: Callable[..., AuthContext],
        table: Table,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        payload = {
            "table": str(table.public_id),
            "guest_count": 2,
            "opened_at": datetime.now(UTC).isoformat(),
            "currency": "UAH",
        }

        response = auth.client.post(URL, payload, content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED

        response = auth.client.post(URL, payload, content_type="application/json")
        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert data["code"] == "table_occupied"

    def test_returns_403_for_customer(
        self,
        api: Callable[..., AuthContext],
        table: Table,
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=table.restaurant_id)
        response = auth.client.post(
            URL,
            {
                "table": str(table.public_id),
                "guest_count": 2,
                "opened_at": datetime.now(UTC).isoformat(),
                "currency": "UAH",
            },
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
