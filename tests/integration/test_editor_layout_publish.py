from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from django.core.cache import cache
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


def _table(
    x: int = 0,
    y: int = 0,
    width: int = 400,
    height: int = 200,
    shape: str = "square",
    capacity: int = 4,
    rotation: int = 0,
    public_number: str = "",
) -> dict[str, Any]:
    return {
        "id": None,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "rotation": rotation,
        "shape": shape,
        "capacity": capacity,
        "zone_id": None,
        "public_number": public_number,
        "tags": [],
    }


TABLE_LAYOUT_A = {
    "tables": [_table(x=10, y=20)],
}

TABLE_LAYOUT_B = {
    "tables": [
        _table(x=10, y=20),
        _table(x=50, y=60, width=600, height=600, shape="round", capacity=6, rotation=90),
    ]
}

TABLE_LAYOUT_C = {
    "tables": [
        _table(x=15, y=25),
        _table(
            x=100, y=200, width=800, height=400,
            shape="rectangle", capacity=8, rotation=180,
        ),
    ]
}


@pytest.mark.django_db
class TestEmitHallLayoutPublished:
    def test_sends_to_correct_group(self, restaurant: Any) -> None:
        cache.clear()
        with patch("common.hall_events.get_channel_layer") as mock_get_layer:
            mock_layer = AsyncMock()
            mock_get_layer.return_value = mock_layer

            emit_hall_layout_published(
                restaurant_id=restaurant.id,
                layout_version_id=1,
                layout_version_public_id="a1b2c3d4-0001-0000-0000-000000000001",
                restaurant_public_id=str(restaurant.public_id),
            )

            mock_layer.group_send.assert_called_once()
            call_args = mock_layer.group_send.call_args
            assert call_args[0][0] == hall_group_name(restaurant.id)
            event = call_args[0][1]["event"]
            assert event["event_name"] == "LAYOUT_PUBLISHED"
            assert event["schema_version"] == "1"
            assert event["layout_version_public_id"] == "a1b2c3d4-0001-0000-0000-000000000001"
            assert event["restaurant_public_id"] == str(restaurant.public_id)
            assert "event_id" in event
            assert "occurred_at" in event

    def test_unique_event_id_per_call(self, restaurant: Any) -> None:
        cache.clear()
        with patch("common.hall_events.get_channel_layer") as mock_get_layer:
            mock_layer = AsyncMock()
            mock_get_layer.return_value = mock_layer

            emit_hall_layout_published(
                restaurant_id=restaurant.id,
                layout_version_id=1,
                layout_version_public_id="a1b2c3d4-0001-0000-0000-000000000001",
                restaurant_public_id=str(restaurant.public_id),
            )
            event_id_1 = mock_layer.group_send.call_args[0][1]["event"]["event_id"]

            emit_hall_layout_published(
                restaurant_id=restaurant.id,
                layout_version_id=2,
                layout_version_public_id="a1b2c3d4-0002-0000-0000-000000000002",
                restaurant_public_id=str(restaurant.public_id),
            )
            event_id_2 = mock_layer.group_send.call_args[0][1]["event"]["event_id"]

            assert event_id_1 != event_id_2

    def test_stable_event_id_for_same_operation(self, restaurant: Any) -> None:
        cache.clear()
        with patch("common.hall_events.get_channel_layer") as mock_get_layer:
            mock_layer = AsyncMock()
            mock_get_layer.return_value = mock_layer

            emit_hall_layout_published(
                restaurant_id=restaurant.id,
                layout_version_id=1,
                layout_version_public_id="a1b2c3d4-0001-0000-0000-000000000001",
                restaurant_public_id=str(restaurant.public_id),
            )
            event_id_1 = mock_layer.group_send.call_args[0][1]["event"]["event_id"]

            emit_hall_layout_published(
                restaurant_id=restaurant.id,
                layout_version_id=1,
                layout_version_public_id="a1b2c3d4-0001-0000-0000-000000000001",
                restaurant_public_id=str(restaurant.public_id),
            )
            event_id_2 = mock_layer.group_send.call_args[0][1]["event"]["event_id"]

            assert event_id_1 == event_id_2

    def test_dedup_skips_duplicate_broadcast(self, restaurant: Any) -> None:
        cache.clear()
        with patch("common.hall_events.get_channel_layer") as mock_get_layer:
            mock_layer = AsyncMock()
            mock_get_layer.return_value = mock_layer

            emit_hall_layout_published(
                restaurant_id=restaurant.id,
                layout_version_id=1,
                layout_version_public_id="a1b2c3d4-0001-0000-0000-000000000001",
                restaurant_public_id=str(restaurant.public_id),
            )
            emit_hall_layout_published(
                restaurant_id=restaurant.id,
                layout_version_id=1,
                layout_version_public_id="a1b2c3d4-0001-0000-0000-000000000001",
                restaurant_public_id=str(restaurant.public_id),
            )

            assert mock_layer.group_send.call_count == 1


@pytest.mark.django_db(databases=["default"], transaction=True)
class TestPublishEndpoint:
    def test_admin_can_publish(self, restaurant: Any) -> None:
        client = _admin_api(restaurant.id)

        with patch("apps.editor.services.emit_hall_layout_published") as mock_emit:
            response = client.post(
                "/api/editor/layouts/publish/",
                TABLE_LAYOUT_A,
                format="json",
            )

        assert response.status_code == 201
        data = response.json()
        assert data["restaurant"] == str(restaurant.public_id)
        assert data["published_by"] is not None
        assert data["public_id"] is not None
        assert data["published_at"] is not None
        assert data["parent_version"] is None
        assert "table_id_map" in data
        assert "warnings" in data

        mock_emit.assert_called_once()

    @pytest.mark.parametrize("role", [RoleCode.WAITER, RoleCode.COOK, RoleCode.CUSTOMER])
    def test_non_admin_gets_forbidden(self, restaurant: Any, role: str) -> None:
        client = _non_admin_api(role, restaurant.id)

        response = client.post(
            "/api/editor/layouts/publish/",
            TABLE_LAYOUT_A,
            format="json",
        )

        assert response.status_code == 403

    def test_unauthenticated_gets_unauthorized(self, restaurant: Any) -> None:
        client = APIClient()

        response = client.post(
            "/api/editor/layouts/publish/",
            TABLE_LAYOUT_A,
            format="json",
        )

        assert response.status_code == 401

    def test_three_publishes_produce_three_rows(self, restaurant: Any) -> None:
        client = _admin_api(restaurant.id)

        with patch("apps.editor.services.emit_hall_layout_published"):
            resp1 = client.post(
                "/api/editor/layouts/publish/",
                TABLE_LAYOUT_A,
                format="json",
            )
            resp2 = client.post(
                "/api/editor/layouts/publish/",
                TABLE_LAYOUT_B,
                format="json",
            )
            resp3 = client.post(
                "/api/editor/layouts/publish/",
                TABLE_LAYOUT_C,
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
                TABLE_LAYOUT_A,
                format="json",
            )
            client.post(
                "/api/editor/layouts/publish/",
                TABLE_LAYOUT_B,
                format="json",
            )
            client.post(
                "/api/editor/layouts/publish/",
                TABLE_LAYOUT_C,
                format="json",
            )

        version_1 = LayoutVersion.objects.get(public_id=resp1.json()["public_id"])
        assert "tables" in version_1.layout_json
        assert len(version_1.layout_json["tables"]) == len(TABLE_LAYOUT_A["tables"])

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

        # Include the existing table in the layout so it doesn't get soft-deleted
        existing_table_entry = _table(
            x=200, y=300, width=400, height=400,
            public_number=table.public_number,
        )
        existing_table_entry["id"] = str(table.public_id)
        layout_with_existing = {
            "tables": [
                {**TABLE_LAYOUT_A["tables"][0]},
                existing_table_entry,
            ]
        }

        client = _admin_api(restaurant.id)

        with patch("apps.editor.services.emit_hall_layout_published"):
            response = client.post(
                "/api/editor/layouts/publish/",
                layout_with_existing,
                format="json",
            )

        assert response.status_code == 201

        session.refresh_from_db()
        assert session.status == SessionStatus.OPEN

    def _make_reservation(self, restaurant: Any, table: Any) -> Any:
        from django.utils import timezone

        from apps.reservations.models import Reservation, ReservationStatus

        return Reservation.objects.create(
            restaurant=restaurant,
            table=table,
            guest_count=2,
            start_at=timezone.now() + timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=3),
            status=ReservationStatus.PENDING,
        )

    def test_moved_table_with_reservation_does_not_conflict(
        self, restaurant: Any, table: Any
    ) -> None:
        """Moving a table (same id, new position) must never trigger the in-use 400."""
        reservation = self._make_reservation(restaurant, table)

        moved = _table(x=900, y=900, public_number=table.public_number)
        moved["id"] = str(table.public_id)

        client = _admin_api(restaurant.id)
        with patch("apps.editor.services.emit_hall_layout_published"):
            response = client.post(
                "/api/editor/layouts/publish/",
                {"tables": [moved], "deleted_table_ids": []},
                format="json",
            )

        assert response.status_code == 201
        table.refresh_from_db()
        assert table.active is True
        reservation.refresh_from_db()
        assert reservation.table_id == table.pk

    def test_table_omitted_without_delete_flag_stays_active(
        self, restaurant: Any, table: Any
    ) -> None:
        """A table absent from the layout but not explicitly deleted is left untouched."""
        self._make_reservation(restaurant, table)

        client = _admin_api(restaurant.id)
        with patch("apps.editor.services.emit_hall_layout_published"):
            response = client.post(
                "/api/editor/layouts/publish/",
                {"tables": [_table(x=10, y=20)], "deleted_table_ids": []},
                format="json",
            )

        assert response.status_code == 201
        table.refresh_from_db()
        assert table.active is True

    def test_explicit_delete_with_reservation_conflicts(
        self, restaurant: Any, table: Any
    ) -> None:
        self._make_reservation(restaurant, table)

        client = _admin_api(restaurant.id)
        with patch("apps.editor.services.emit_hall_layout_published"):
            response = client.post(
                "/api/editor/layouts/publish/",
                {"tables": [], "deleted_table_ids": [str(table.public_id)]},
                format="json",
            )

        assert response.status_code == 400
        assert "active reservations or sessions" in response.json()["detail"]
        table.refresh_from_db()
        assert table.active is True

    def test_explicit_delete_without_reservation_deactivates(
        self, restaurant: Any, table: Any
    ) -> None:
        client = _admin_api(restaurant.id)
        with patch("apps.editor.services.emit_hall_layout_published"):
            response = client.post(
                "/api/editor/layouts/publish/",
                {"tables": [], "deleted_table_ids": [str(table.public_id)]},
                format="json",
            )

        assert response.status_code == 201
        table.refresh_from_db()
        assert table.active is False

    def test_deleted_table_ids_not_persisted_in_payload(
        self, restaurant: Any, table: Any
    ) -> None:
        client = _admin_api(restaurant.id)
        with patch("apps.editor.services.emit_hall_layout_published"):
            response = client.post(
                "/api/editor/layouts/publish/",
                {"tables": [], "deleted_table_ids": [str(table.public_id)]},
                format="json",
            )

        version = LayoutVersion.objects.get(public_id=response.json()["public_id"])
        assert "deleted_table_ids" not in version.layout_json

    def test_parent_version_linked_on_second_publish(self, restaurant: Any) -> None:
        client = _admin_api(restaurant.id)

        with patch("apps.editor.services.emit_hall_layout_published"):
            resp1 = client.post(
                "/api/editor/layouts/publish/",
                TABLE_LAYOUT_A,
                format="json",
            )
            resp2 = client.post(
                "/api/editor/layouts/publish/",
                TABLE_LAYOUT_B,
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
                TABLE_LAYOUT_A,
                format="json",
            )
            client.post(
                "/api/editor/layouts/publish/",
                TABLE_LAYOUT_B,
                format="json",
            )
            client.post(
                "/api/editor/layouts/publish/",
                TABLE_LAYOUT_C,
                format="json",
            )

        assert mock_emit.call_count == 3
        for call_args in mock_emit.call_args_list:
            assert call_args[1]["restaurant_id"] == restaurant.id
            assert "layout_version_id" in call_args[1]
