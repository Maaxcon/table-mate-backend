from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from rest_framework.test import APIClient

from apps.authentication.models import RoleCode
from apps.authentication.services import issue_tokens_with_restaurant
from apps.editor.models import LayoutVersion
from common.channels import hall_group_name
from common.hall_events import emit_hall_layout_published
from tests.conftest import UserFactory


def _admin_api(restaurant_id: int) -> APIClient:
    user = UserFactory.build(role=RoleCode.ADMIN)
    user.save()
    client = APIClient()
    access, _ = issue_tokens_with_restaurant(user, restaurant_id)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _non_admin_api(role: str, restaurant_id: int) -> APIClient:
    user = UserFactory.build(role=role)
    user.save()
    client = APIClient()
    if restaurant_id is not None:
        access, _ = issue_tokens_with_restaurant(user, restaurant_id)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    else:
        client.force_authenticate(user=user)
    return client


TABLE_LAYOUT_A = {
    "tables": [
        {"id": "t1", "x": 10, "y": 20, "w": 4, "h": 2, "rotation": 0, "capacity": 4, "sector": "main"},
    ]
}

TABLE_LAYOUT_B = {
    "tables": [
        {"id": "t1", "x": 10, "y": 20, "w": 4, "h": 2, "rotation": 0, "capacity": 4, "sector": "main"},
        {"id": "t2", "x": 50, "y": 60, "w": 6, "h": 3, "rotation": 90, "capacity": 6, "sector": "patio"},
    ]
}

TABLE_LAYOUT_C = {
    "tables": [
        {"id": "t1", "x": 15, "y": 25, "w": 4, "h": 2, "rotation": 0, "capacity": 4, "sector": "main"},
        {"id": "t3", "x": 100, "y": 200, "w": 8, "h": 4, "rotation": 180, "capacity": 8, "sector": "vip"},
    ]
}


@pytest.mark.django_db
class TestEmitHallLayoutPublished:
    def test_sends_to_correct_group(self, restaurant: Any) -> None:
        with patch("common.hall_events.get_channel_layer") as mock_get_layer:
            mock_layer = AsyncMock()
            mock_get_layer.return_value = mock_layer

            emit_hall_layout_published(
                restaurant_id=restaurant.id,
                layout_version_id=1,
            )

            mock_layer.group_send.assert_called_once()
            call_args = mock_layer.group_send.call_args
            assert call_args[0][0] == hall_group_name(restaurant.id)
            event = call_args[0][1]["event"]
            assert event["event_name"] == "LAYOUT_PUBLISHED"
            assert event["schema_version"] == "1"
            assert event["layout_version_id"] == 1
            assert event["restaurant_id"] == restaurant.id
            assert "event_id" in event
            assert "occurred_at" in event

    def test_unique_event_id_per_call(self, restaurant: Any) -> None:
        with patch("common.hall_events.get_channel_layer") as mock_get_layer:
            mock_layer = AsyncMock()
            mock_get_layer.return_value = mock_layer

            emit_hall_layout_published(restaurant_id=restaurant.id, layout_version_id=1)
            event_id_1 = mock_layer.group_send.call_args[0][1]["event"]["event_id"]

            emit_hall_layout_published(restaurant_id=restaurant.id, layout_version_id=2)
            event_id_2 = mock_layer.group_send.call_args[0][1]["event"]["event_id"]

            assert event_id_1 != event_id_2


@pytest.mark.django_db(databases=["default"], transaction=True)
class TestPublishEndpoint:
    def test_admin_can_publish(self, restaurant: Any) -> None:
        client = _admin_api(restaurant.id)

        with patch("apps.editor.services.emit_hall_layout_published") as mock_emit:
            response = client.post(
                "/api/editor/layouts/publish/",
                {"layout_json": TABLE_LAYOUT_A},
                format="json",
            )

        assert response.status_code == 201
        data = response.json()
        assert data["layout_json"]["diff"] is None
        assert data["layout_json"]["entities"] == TABLE_LAYOUT_A["tables"]
        assert data["restaurant"] == str(restaurant.public_id)
        assert data["published_by"] is not None
        assert data["public_id"] is not None
        assert data["published_at"] is not None
        assert data["parent_version"] is None

        mock_emit.assert_called_once()

    @pytest.mark.parametrize("role", [RoleCode.WAITER, RoleCode.COOK, RoleCode.CUSTOMER])
    def test_non_admin_gets_forbidden(self, restaurant: Any, role: str) -> None:
        client = _non_admin_api(role, restaurant.id)

        response = client.post(
            "/api/editor/layouts/publish/",
            {"layout_json": TABLE_LAYOUT_A},
            format="json",
        )

        assert response.status_code == 403

    def test_unauthenticated_gets_unauthorized(self, restaurant: Any) -> None:
        client = APIClient()

        response = client.post(
            "/api/editor/layouts/publish/",
            {"layout_json": TABLE_LAYOUT_A},
            format="json",
        )

        assert response.status_code == 401

    def test_three_publishes_produce_three_rows(self, restaurant: Any) -> None:
        client = _admin_api(restaurant.id)

        with patch("apps.editor.services.emit_hall_layout_published"):
            resp1 = client.post(
                "/api/editor/layouts/publish/",
                {"layout_json": TABLE_LAYOUT_A},
                format="json",
            )
            resp2 = client.post(
                "/api/editor/layouts/publish/",
                {"layout_json": TABLE_LAYOUT_B},
                format="json",
            )
            resp3 = client.post(
                "/api/editor/layouts/publish/",
                {"layout_json": TABLE_LAYOUT_C},
                format="json",
            )

        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp3.status_code == 201

        assert LayoutVersion.objects.count() == 3

    def test_older_rows_remain_unchanged(self, restaurant: Any) -> None:
        client = _admin_api(restaurant.id)

        with patch("apps.editor.services.emit_hall_layout_published"):
            resp1 = client.post(
                "/api/editor/layouts/publish/",
                {"layout_json": TABLE_LAYOUT_A},
                format="json",
            )
            client.post(
                "/api/editor/layouts/publish/",
                {"layout_json": TABLE_LAYOUT_B},
                format="json",
            )
            client.post(
                "/api/editor/layouts/publish/",
                {"layout_json": TABLE_LAYOUT_C},
                format="json",
            )

        version_1 = LayoutVersion.objects.get(public_id=resp1.json()["public_id"])
        assert version_1.layout_json["diff"] is None
        assert version_1.layout_json["entities"] == TABLE_LAYOUT_A["tables"]

    def test_active_sessions_unaffected(self, restaurant: Any, table: Any) -> None:
        from django.utils import timezone

        from apps.orders.models import Session, SessionStatus
        from apps.reservations.models import Reservation, ReservationStatus

        reservation = Reservation.objects.create(
            restaurant=restaurant,
            table=table,
            guest_count=2,
            start_at=timezone.now() - timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=2),
            status=ReservationStatus.ACTIVE,
        )

        session = Session.objects.create(
            restaurant=restaurant,
            table=table,
            reservation=reservation,
            guest_count=2,
            status=SessionStatus.OPEN,
            currency="UAH",
            opened_at=timezone.now(),
        )

        client = _admin_api(restaurant.id)

        with patch("apps.editor.services.emit_hall_layout_published"):
            response = client.post(
                "/api/editor/layouts/publish/",
                {"layout_json": TABLE_LAYOUT_A},
                format="json",
            )

        assert response.status_code == 201

        session.refresh_from_db()
        assert session.status == SessionStatus.OPEN

    def test_parent_version_linked_on_second_publish(self, restaurant: Any) -> None:
        client = _admin_api(restaurant.id)

        with patch("apps.editor.services.emit_hall_layout_published"):
            resp1 = client.post(
                "/api/editor/layouts/publish/",
                {"layout_json": TABLE_LAYOUT_A},
                format="json",
            )
            resp2 = client.post(
                "/api/editor/layouts/publish/",
                {"layout_json": TABLE_LAYOUT_B},
                format="json",
            )

        v1_pk = LayoutVersion.objects.get(public_id=resp1.json()["public_id"]).pk
        v2 = LayoutVersion.objects.get(public_id=resp2.json()["public_id"])
        assert v2.parent_version_id == v1_pk

    def test_each_publish_emits_hall_event(self, restaurant: Any) -> None:
        client = _admin_api(restaurant.id)

        with patch("apps.editor.services.emit_hall_layout_published") as mock_emit:
            client.post(
                "/api/editor/layouts/publish/",
                {"layout_json": TABLE_LAYOUT_A},
                format="json",
            )
            client.post(
                "/api/editor/layouts/publish/",
                {"layout_json": TABLE_LAYOUT_B},
                format="json",
            )
            client.post(
                "/api/editor/layouts/publish/",
                {"layout_json": TABLE_LAYOUT_C},
                format="json",
            )

        assert mock_emit.call_count == 3
        for call_args in mock_emit.call_args_list:
            assert call_args[1]["restaurant_id"] == restaurant.id
            assert "layout_version_id" in call_args[1]
