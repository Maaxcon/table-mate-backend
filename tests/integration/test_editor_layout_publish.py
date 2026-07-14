from __future__ import annotations

from datetime import timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.authentication.models import RoleCode
from apps.authentication.services import issue_tokens_with_restaurant
from apps.editor.models import LayoutVersion
from apps.restaurants.models import Restaurant, Table
from common.channels import hall_group_name
from common.hall_events import emit_hall_layout_published, emit_hall_zone_updated
from tests.conftest import RestaurantFactory, UserFactory


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
    *,
    zone_id: str | None = None,
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
        "zone_id": zone_id,
        "public_number": public_number,
        "tags": [],
    }


def _layout_a(zone_id: str) -> dict[str, Any]:
    return {"tables": [_table(x=10, y=20, zone_id=zone_id)]}


def _layout_b(zone_id: str) -> dict[str, Any]:
    return {
        "tables": [
            _table(x=10, y=20, zone_id=zone_id),
            _table(x=50, y=60, width=600, height=600, shape="round", capacity=6, rotation=90, zone_id=zone_id),
        ]
    }


def _layout_c(zone_id: str) -> dict[str, Any]:
    return {
        "tables": [
            _table(x=15, y=25, zone_id=zone_id),
            _table(
                x=100,
                y=200,
                width=800,
                height=400,
                shape="rectangle",
                capacity=8,
                rotation=180,
                zone_id=zone_id,
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


@pytest.mark.django_db
class TestEmitHallZoneUpdated:
    def test_distinct_saves_produce_distinct_event_ids(self, restaurant: Any) -> None:
        # Repeated renames of the SAME zone must each broadcast. The event_id varies by
        # updated_at, so the dedup gate does not collapse separate saves into one.
        cache.clear()
        with patch("common.hall_events.get_channel_layer") as mock_get_layer:
            mock_layer = AsyncMock()
            mock_get_layer.return_value = mock_layer

            zone_public_id = "a1b2c3d4-0001-0000-0000-000000000001"
            emit_hall_zone_updated(
                restaurant_id=restaurant.id,
                zone_public_id=zone_public_id,
                zone_name="Patio",
                zone_updated_at="2026-06-26T10:00:00+00:00",
            )
            emit_hall_zone_updated(
                restaurant_id=restaurant.id,
                zone_public_id=zone_public_id,
                zone_name="Terrace",
                zone_updated_at="2026-06-26T10:00:05+00:00",
            )

            assert mock_layer.group_send.call_count == 2
            ids = [c[0][1]["event"]["event_id"] for c in mock_layer.group_send.call_args_list]
            assert ids[0] != ids[1]

    def test_same_save_dedups(self, restaurant: Any) -> None:
        # Re-sending the identical save (same updated_at) is still idempotent.
        cache.clear()
        with patch("common.hall_events.get_channel_layer") as mock_get_layer:
            mock_layer = AsyncMock()
            mock_get_layer.return_value = mock_layer

            kwargs = {
                "restaurant_id": restaurant.id,
                "zone_public_id": "a1b2c3d4-0001-0000-0000-000000000001",
                "zone_name": "Patio",
                "zone_updated_at": "2026-06-26T10:00:00+00:00",
            }
            emit_hall_zone_updated(**kwargs)
            emit_hall_zone_updated(**kwargs)

            assert mock_layer.group_send.call_count == 1


@pytest.mark.django_db(databases=["default"], transaction=True)
class TestPublishEndpoint:
    def test_new_table_with_non_uuid_client_id_publishes(self, restaurant: Any, zone: Any) -> None:
        # A brand-new table carries the editor's throwaway local id (not a UUID) in _client_id.
        # Publish must succeed and create the table, echoing the client handle back for the
        # frontend to reconcile its row with the server-assigned public_id.
        client = _admin_api(restaurant.id)
        client_id = "1723456789123-abc1d2"
        table = _table(x=10, y=20, zone_id=str(zone.public_id))
        table["_client_id"] = client_id

        with patch("apps.editor.services.emit_hall_layout_published"):
            response = client.post(
                "/api/editor/layouts/publish/",
                {"tables": [table]},
                format="json",
            )

        assert response.status_code == 201, response.json()
        data = response.json()
        assert Table.objects.filter(restaurant_id=restaurant.id, active=True).count() == 1
        assert client_id in data["public_number_map"]

    def test_admin_can_publish(self, restaurant: Any, zone: Any) -> None:
        client = _admin_api(restaurant.id)

        with patch("apps.editor.services.emit_hall_layout_published") as mock_emit:
            response = client.post(
                "/api/editor/layouts/publish/",
                _layout_a(str(zone.public_id)),
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

        mock_emit.assert_called_once()

    @pytest.mark.parametrize("role", [RoleCode.WAITER, RoleCode.COOK, RoleCode.CUSTOMER])
    def test_non_admin_gets_forbidden(self, restaurant: Any, role: str) -> None:
        client = _non_admin_api(role, restaurant.id)

        response = client.post(
            "/api/editor/layouts/publish/",
            _layout_a(""),
            format="json",
        )

        assert response.status_code == 403

    def test_unauthenticated_gets_unauthorized(self, restaurant: Any) -> None:
        client = APIClient()

        response = client.post(
            "/api/editor/layouts/publish/",
            _layout_a(""),
            format="json",
        )

        assert response.status_code == 401

    def test_three_publishes_produce_three_rows(self, restaurant: Any, zone: Any) -> None:
        zid = str(zone.public_id)
        client = _admin_api(restaurant.id)

        with patch("apps.editor.services.emit_hall_layout_published"):
            resp1 = client.post(
                "/api/editor/layouts/publish/",
                _layout_a(zid),
                format="json",
            )
            resp2 = client.post(
                "/api/editor/layouts/publish/",
                _layout_b(zid),
                format="json",
            )
            resp3 = client.post(
                "/api/editor/layouts/publish/",
                _layout_c(zid),
                format="json",
            )

        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp3.status_code == 201

        assert LayoutVersion.objects.count() == 3

    def test_older_rows_remain_unchanged(self, restaurant: Any, zone: Any) -> None:
        zid = str(zone.public_id)
        client = _admin_api(restaurant.id)

        with patch("apps.editor.services.emit_hall_layout_published"):
            resp1 = client.post(
                "/api/editor/layouts/publish/",
                _layout_a(zid),
                format="json",
            )
            client.post(
                "/api/editor/layouts/publish/",
                _layout_b(zid),
                format="json",
            )
            client.post(
                "/api/editor/layouts/publish/",
                _layout_c(zid),
                format="json",
            )

        version_1 = LayoutVersion.objects.get(public_id=resp1.json()["public_id"])
        assert "tables" in version_1.layout_json
        assert len(version_1.layout_json["tables"]) == len(_layout_a(zid)["tables"])

    def test_active_sessions_unaffected(self, restaurant: Any, table: Any, zone: Any) -> None:
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
            reservation_id=reservation.pk,
            guest_count=2,
            status=SessionStatus.OPEN,
            currency="UAH",
            opened_at=timezone.now(),
            ends_at=reservation.end_at,
        )

        # Capture pre-publish FK values for comparison
        session_table_id = session.table_id
        session_restaurant_id = session.restaurant_id
        session_guest_count = session.guest_count
        session_reservation_id = session.reservation_id

        # Include the existing table in the layout so it doesn't get soft-deleted
        existing_table_entry = _table(
            x=200,
            y=300,
            width=400,
            height=400,
            public_number=table.public_number,
            zone_id=str(zone.public_id),
        )
        existing_table_entry["id"] = str(table.public_id)
        layout_with_existing = {
            "tables": [
                {**_layout_a(str(zone.public_id))["tables"][0]},
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
        assert session.table_id == session_table_id
        assert session.restaurant_id == session_restaurant_id
        assert session.guest_count == session_guest_count
        assert session.reservation_id == session_reservation_id

        reservation.refresh_from_db()
        assert reservation.status == ReservationStatus.ACTIVE

        table.refresh_from_db()
        assert table.active is True

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

    def test_moved_table_with_reservation_does_not_conflict(self, restaurant: Any, table: Any) -> None:
        """Moving a table (same id, new position) must never trigger the in-use 400."""
        reservation = self._make_reservation(restaurant, table)

        moved = _table(x=900, y=900, public_number=table.public_number, zone_id=str(table.zone.public_id))
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

    def test_table_omitted_without_delete_flag_stays_active(self, restaurant: Any, table: Any) -> None:
        """A table absent from the layout but not explicitly deleted is left untouched."""
        self._make_reservation(restaurant, table)

        client = _admin_api(restaurant.id)
        with patch("apps.editor.services.emit_hall_layout_published"):
            response = client.post(
                "/api/editor/layouts/publish/",
                {"tables": [_table(x=10, y=20, zone_id=str(table.zone.public_id))], "deleted_table_ids": []},
                format="json",
            )

        assert response.status_code == 201
        table.refresh_from_db()
        assert table.active is True

    def test_explicit_delete_with_reservation_conflicts(self, restaurant: Any, table: Any) -> None:
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

    def test_explicit_delete_without_reservation_deactivates(self, restaurant: Any, table: Any) -> None:
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

    def test_deleted_table_ids_not_persisted_in_payload(self, restaurant: Any, table: Any) -> None:
        client = _admin_api(restaurant.id)
        with patch("apps.editor.services.emit_hall_layout_published"):
            response = client.post(
                "/api/editor/layouts/publish/",
                {"tables": [], "deleted_table_ids": [str(table.public_id)]},
                format="json",
            )

        version = LayoutVersion.objects.get(public_id=response.json()["public_id"])
        assert "deleted_table_ids" not in version.layout_json

    def test_parent_version_linked_on_second_publish(self, restaurant: Any, zone: Any) -> None:
        zid = str(zone.public_id)
        client = _admin_api(restaurant.id)

        with patch("apps.editor.services.emit_hall_layout_published"):
            resp1 = client.post(
                "/api/editor/layouts/publish/",
                _layout_a(zid),
                format="json",
            )
            resp2 = client.post(
                "/api/editor/layouts/publish/",
                _layout_b(zid),
                format="json",
            )

        v1_pk = LayoutVersion.objects.get(public_id=resp1.json()["public_id"]).pk
        v2 = LayoutVersion.objects.get(public_id=resp2.json()["public_id"])
        assert v2.parent_version_id == v1_pk

    def test_each_publish_emits_hall_event(self, restaurant: Any, zone: Any) -> None:
        zid = str(zone.public_id)
        client = _admin_api(restaurant.id)

        with patch("common.hall_events.get_channel_layer") as mock_get_layer:
            mock_layer = AsyncMock()
            mock_get_layer.return_value = mock_layer

            resp1 = client.post(
                "/api/editor/layouts/publish/",
                _layout_a(zid),
                format="json",
            )
            resp2 = client.post(
                "/api/editor/layouts/publish/",
                _layout_b(zid),
                format="json",
            )
            resp3 = client.post(
                "/api/editor/layouts/publish/",
                _layout_c(zid),
                format="json",
            )

        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp3.status_code == 201

        assert mock_layer.group_send.call_count == 3
        for call_args in mock_layer.group_send.call_args_list:
            event = call_args[0][1]["event"]
            assert event["event_name"] == "LAYOUT_PUBLISHED"
            assert event["restaurant_public_id"] == str(restaurant.public_id)
            assert "layout_version_public_id" in event

    # ------------------------------------------------------------------
    # Cross-tenant isolation
    # ------------------------------------------------------------------

    def test_cross_tenant_delete_isolation(self, restaurant: Any, zone: Any) -> None:
        from apps.restaurants.models import Zone

        other_restaurant = cast(Restaurant, RestaurantFactory())  # type: ignore[no-untyped-call]
        other_zone = Zone.objects.create(restaurant=other_restaurant, name="Main Hall")
        other_table = Table.objects.create(
            restaurant=other_restaurant,
            public_number="X001",
            capacity=4,
            zone=other_zone,
        )

        client = _admin_api(restaurant.id)
        with patch("apps.editor.services.emit_hall_layout_published"):
            response = client.post(
                "/api/editor/layouts/publish/",
                {
                    "tables": [_table(x=10, y=20, zone_id=str(zone.public_id))],
                    "deleted_table_ids": [str(other_table.public_id)],
                },
                format="json",
            )

        assert response.status_code == 201
        other_table.refresh_from_db()
        assert other_table.active is True

    # ------------------------------------------------------------------
    # Validation rejection
    # ------------------------------------------------------------------

    def test_rejects_out_of_bounds_table(self, restaurant: Any, zone: Any) -> None:
        zid = str(zone.public_id)
        client = _admin_api(restaurant.id)
        payload = {"tables": [_table(x=2500, y=2500, zone_id=zid)]}
        response = client.post(
            "/api/editor/layouts/publish/",
            payload,
            format="json",
        )
        assert response.status_code == 400

    def test_rejects_round_table_mismatched_dimensions(self, restaurant: Any, zone: Any) -> None:
        zid = str(zone.public_id)
        client = _admin_api(restaurant.id)
        payload = {"tables": [_table(width=400, height=200, shape="round", zone_id=zid)]}
        response = client.post(
            "/api/editor/layouts/publish/",
            payload,
            format="json",
        )
        assert response.status_code == 400

    def test_rejects_zero_capacity(self, restaurant: Any, zone: Any) -> None:
        zid = str(zone.public_id)
        client = _admin_api(restaurant.id)
        payload = {"tables": [_table(capacity=0, zone_id=zid)]}
        response = client.post(
            "/api/editor/layouts/publish/",
            payload,
            format="json",
        )
        assert response.status_code == 400

    def test_rejects_invalid_shape(self, restaurant: Any, zone: Any) -> None:
        zid = str(zone.public_id)
        client = _admin_api(restaurant.id)
        payload = {"tables": [_table(shape="triangle", zone_id=zid)]}
        response = client.post(
            "/api/editor/layouts/publish/",
            payload,
            format="json",
        )
        assert response.status_code == 400

    def test_rotation_360_is_accepted_and_normalized_to_zero(
        self, restaurant: Any, zone: Any
    ) -> None:
        # 360 degrees is the same angle as 0 — a bare max_value=359 bound used
        # to reject it outright even though it's a perfectly valid rotation.
        zid = str(zone.public_id)
        client = _admin_api(restaurant.id)
        payload = {"tables": [_table(rotation=360, zone_id=zid)]}

        with patch("apps.editor.services.emit_hall_layout_published"):
            response = client.post(
                "/api/editor/layouts/publish/",
                payload,
                format="json",
            )

        assert response.status_code == 201, response.json()
        version = LayoutVersion.objects.get(public_id=response.json()["public_id"])
        assert version.layout_json["tables"][0]["rotation"] == 0

    def test_rotation_extreme_negative_is_normalized_not_stored_raw(
        self, restaurant: Any, zone: Any
    ) -> None:
        # No min_value meant an unbounded negative like -1000000 sailed
        # through un-normalized. Normalizing via modulo maps it to its
        # canonical angle instead of storing nonsense.
        zid = str(zone.public_id)
        client = _admin_api(restaurant.id)
        payload = {"tables": [_table(rotation=-1000000, zone_id=zid)]}

        with patch("apps.editor.services.emit_hall_layout_published"):
            response = client.post(
                "/api/editor/layouts/publish/",
                payload,
                format="json",
            )

        assert response.status_code == 201, response.json()
        version = LayoutVersion.objects.get(public_id=response.json()["public_id"])
        rotation = version.layout_json["tables"][0]["rotation"]
        assert rotation == -1000000 % 360
        assert 0 <= rotation < 360
