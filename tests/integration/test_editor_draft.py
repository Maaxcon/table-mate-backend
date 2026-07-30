from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.authentication.models import RoleCode
from apps.authentication.services import issue_tokens_with_restaurant
from apps.editor.models import LayoutDraft, LayoutVersion
from apps.restaurants.models import Table
from tests.conftest import UserFactory


class _EditorAPIClient(APIClient):
    def __init__(self, restaurant_id: int) -> None:
        super().__init__()
        self.restaurant_id = restaurant_id

    def post(self, path: str, data: Any = None, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        if path == "/api/editor/layouts/publish/" and isinstance(data, dict) and "base_layout_version_id" not in data:
            latest = (
                LayoutVersion.objects.filter(restaurant_id=self.restaurant_id).order_by("-published_at", "-id").first()
            )
            data = {**data, "base_layout_version_id": str(latest.public_id) if latest else None}
        return super().post(path, data, *args, **kwargs)

    def put(self, path: str, data: Any = None, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        if path == "/api/editor/layouts/draft/" and isinstance(data, dict) and "base_layout_version_id" not in data:
            latest = (
                LayoutVersion.objects.filter(restaurant_id=self.restaurant_id).order_by("-published_at", "-id").first()
            )
            data = {**data, "base_layout_version_id": str(latest.public_id) if latest else None}
        return super().put(path, data, *args, **kwargs)


def _admin_api(restaurant_id: int) -> APIClient:
    client, _ = _admin_api_with_user(restaurant_id)
    return client


def _admin_api_with_user(restaurant_id: int) -> tuple[APIClient, Any]:
    user = UserFactory.build(role=RoleCode.ADMIN)
    user.save()
    client = _EditorAPIClient(restaurant_id)
    access, _ = issue_tokens_with_restaurant(user, restaurant_id)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client, user


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


@pytest.mark.django_db(transaction=True)
class TestDraftEndpoint:
    """GET /api/editor/layouts/draft/ — load draft or fallback to published."""

    def test_get_draft_returns_draft_when_exists(self, restaurant: Any, zone: Any) -> None:
        client = _admin_api(restaurant.id)
        payload = _layout_a(str(zone.public_id))

        # Save a draft first
        client.put("/api/editor/layouts/draft/", payload, format="json")

        # Load it back
        response = client.get("/api/editor/layouts/draft/")
        assert response.status_code == 200
        data = response.json()
        assert data["draft_json"] is not None
        assert data["is_draft"] is True
        assert data["updated_at"] is not None
        assert "tables" in data["draft_json"]

    def test_get_draft_fallsback_to_published_when_no_draft(self, restaurant: Any, zone: Any) -> None:
        from unittest.mock import patch

        client = _admin_api(restaurant.id)

        # Publish a layout first
        with patch("apps.editor.services.emit_hall_layout_published"):
            client.post(
                "/api/editor/layouts/publish/",
                _layout_a(str(zone.public_id)),
                format="json",
            )

        # No draft — should return the latest published layout
        response = client.get("/api/editor/layouts/draft/")
        assert response.status_code == 200
        data = response.json()
        assert data["draft_json"] is not None
        assert data["is_draft"] is False
        assert data["updated_at"] is None
        assert data["owner_id"] is None

    def test_get_draft_returns_none_when_nothing_exists(self, restaurant: Any, zone: Any) -> None:
        client = _admin_api(restaurant.id)

        response = client.get("/api/editor/layouts/draft/")
        assert response.status_code == 200
        data = response.json()
        assert data["draft_json"] is None
        assert data["is_draft"] is False
        assert data["updated_at"] is None

    def test_get_draft_requires_auth(self, restaurant: Any) -> None:
        client = APIClient()
        response = client.get("/api/editor/layouts/draft/")
        assert response.status_code == 401

    def test_waiter_cannot_read_draft(self, restaurant: Any) -> None:
        client = _non_admin_api(RoleCode.WAITER, restaurant.id)
        response = client.get("/api/editor/layouts/draft/")
        assert response.status_code == 403

    def test_admin_only_loads_their_own_draft(self, restaurant: Any, zone: Any) -> None:
        first_admin, _ = _admin_api_with_user(restaurant.id)
        second_admin, _ = _admin_api_with_user(restaurant.id)
        zone_id = str(zone.public_id)

        first_admin.put("/api/editor/layouts/draft/", _layout_a(zone_id), format="json")
        second_admin.put(
            "/api/editor/layouts/draft/",
            {"tables": [_table(x=99, y=99, zone_id=zone_id)]},
            format="json",
        )

        first_draft = first_admin.get("/api/editor/layouts/draft/").json()
        second_draft = second_admin.get("/api/editor/layouts/draft/").json()

        assert LayoutDraft.objects.filter(restaurant=restaurant).count() == 2
        assert first_draft["draft_json"]["tables"][0]["x"] == 10
        assert second_draft["draft_json"]["tables"][0]["x"] == 99

    def test_cook_cannot_read_draft(self, restaurant: Any) -> None:
        client = _non_admin_api(RoleCode.COOK, restaurant.id)
        response = client.get("/api/editor/layouts/draft/")
        assert response.status_code == 403


@pytest.mark.django_db(transaction=True)
class TestSaveDraftEndpoint:
    """PUT /api/editor/layouts/draft/ — save draft."""

    def test_admin_can_save_draft(self, restaurant: Any, zone: Any) -> None:
        client = _admin_api(restaurant.id)
        payload = _layout_a(str(zone.public_id))

        response = client.put("/api/editor/layouts/draft/", payload, format="json")
        assert response.status_code == 200
        data = response.json()
        assert data["draft_json"] is not None
        assert "tables" in data["draft_json"]
        assert data["updated_at"] is not None

        # Verify no Table rows were created (draft only, not published)
        assert Table.objects.filter(restaurant_id=restaurant.id).count() == 0

    def test_save_draft_overwrites_previous(self, restaurant: Any, zone: Any) -> None:
        client = _admin_api(restaurant.id)
        zid = str(zone.public_id)
        payload_a = _layout_a(zid)

        # First save
        client.put("/api/editor/layouts/draft/", payload_a, format="json")

        # Second save with different data
        payload_b = {"tables": [_table(x=99, y=99, zone_id=zid)]}
        response = client.put("/api/editor/layouts/draft/", payload_b, format="json")
        assert response.status_code == 200
        tables = response.json()["draft_json"]["tables"]
        assert tables[0]["x"] == 99

        # Only one draft row exists
        assert LayoutDraft.objects.count() == 1

    def test_save_draft_rejects_invalid_data(self, restaurant: Any) -> None:
        client = _admin_api(restaurant.id)
        payload = {"tables": [{"shape": "triangle"}]}
        response = client.put("/api/editor/layouts/draft/", payload, format="json")
        assert response.status_code == 400

    def test_save_draft_requires_admin(self, restaurant: Any) -> None:
        client = _non_admin_api(RoleCode.WAITER, restaurant.id)
        response = client.put("/api/editor/layouts/draft/", {"tables": []}, format="json")
        assert response.status_code == 403

    def test_save_draft_requires_auth(self, restaurant: Any) -> None:
        client = APIClient()
        response = client.put("/api/editor/layouts/draft/", {"tables": []}, format="json")
        assert response.status_code == 401

    def test_draft_does_not_affect_live_layout(self, restaurant: Any, zone: Any) -> None:
        from unittest.mock import patch

        client = _admin_api(restaurant.id)

        # Publish initial layout
        with patch("apps.editor.services.emit_hall_layout_published"):
            client.post(
                "/api/editor/layouts/publish/",
                _layout_a(str(zone.public_id)),
                format="json",
            )

        # Save draft with different data
        payload = {"tables": [_table(x=999, y=999, zone_id=str(zone.public_id))]}
        client.put("/api/editor/layouts/draft/", payload, format="json")

        # Live layout should still return the published version
        response = client.get("/api/editor/layouts/latest/")
        assert response.status_code == 200
        tables = response.json()["layout_json"]["tables"]
        assert tables[0]["x"] == 10  # original published value, not draft

    def test_stale_draft_save_is_rejected_and_preserves_existing_draft(self, restaurant: Any, zone: Any) -> None:
        from unittest.mock import patch

        publisher, _ = _admin_api_with_user(restaurant.id)
        editor, _ = _admin_api_with_user(restaurant.id)
        zone_id = str(zone.public_id)

        with patch("apps.editor.services.emit_hall_layout_published"):
            first_publish = publisher.post("/api/editor/layouts/publish/", _layout_a(zone_id), format="json")
            base_version_id = first_publish.json()["public_id"]
            editor.put(
                "/api/editor/layouts/draft/",
                {"tables": [_table(x=50, y=50, zone_id=zone_id)], "base_layout_version_id": base_version_id},
                format="json",
            )
            publisher.post("/api/editor/layouts/publish/", _layout_a(zone_id), format="json")
            stale_save = editor.put(
                "/api/editor/layouts/draft/",
                {"tables": [_table(x=99, y=99, zone_id=zone_id)], "base_layout_version_id": base_version_id},
                format="json",
            )

        assert stale_save.status_code == 409
        assert editor.get("/api/editor/layouts/draft/").json()["draft_json"]["tables"][0]["x"] == 50


@pytest.mark.django_db(transaction=True)
class TestDeleteDraftEndpoint:
    """DELETE /api/editor/layouts/draft/ — discard draft."""

    def test_admin_can_discard_draft(self, restaurant: Any, zone: Any) -> None:
        client = _admin_api(restaurant.id)

        # Save a draft
        client.put(
            "/api/editor/layouts/draft/",
            _layout_a(str(zone.public_id)),
            format="json",
        )
        assert LayoutDraft.objects.count() == 1

        # Discard it
        response = client.delete("/api/editor/layouts/draft/")
        assert response.status_code == 204
        assert LayoutDraft.objects.count() == 0

    def test_discard_with_no_draft_is_noop(self, restaurant: Any) -> None:
        client = _admin_api(restaurant.id)

        response = client.delete("/api/editor/layouts/draft/")
        assert response.status_code == 204

    def test_discard_requires_admin(self, restaurant: Any) -> None:
        client = _non_admin_api(RoleCode.WAITER, restaurant.id)
        response = client.delete("/api/editor/layouts/draft/")
        assert response.status_code == 403

    def test_discard_does_not_affect_tables(self, restaurant: Any, zone: Any) -> None:
        from unittest.mock import patch

        client = _admin_api(restaurant.id)

        # Publish a table
        with patch("apps.editor.services.emit_hall_layout_published"):
            client.post(
                "/api/editor/layouts/publish/",
                _layout_a(str(zone.public_id)),
                format="json",
            )

        # Save and discard draft
        client.put(
            "/api/editor/layouts/draft/",
            _layout_a(str(zone.public_id)),
            format="json",
        )
        client.delete("/api/editor/layouts/draft/")

        # Table should still exist
        assert Table.objects.filter(restaurant_id=restaurant.id, active=True).count() == 1

    def test_discard_only_deletes_current_admin_draft(self, restaurant: Any, zone: Any) -> None:
        first_admin, _ = _admin_api_with_user(restaurant.id)
        second_admin, _ = _admin_api_with_user(restaurant.id)
        payload = _layout_a(str(zone.public_id))

        first_admin.put("/api/editor/layouts/draft/", payload, format="json")
        second_admin.put("/api/editor/layouts/draft/", payload, format="json")

        response = first_admin.delete("/api/editor/layouts/draft/")

        assert response.status_code == 204
        assert LayoutDraft.objects.filter(restaurant=restaurant).count() == 1
        assert second_admin.get("/api/editor/layouts/draft/").json()["is_draft"] is True


@pytest.mark.django_db(transaction=True)
class TestDraftClearedOnPublish:
    """Draft must be deleted after a successful publish."""

    def test_draft_deleted_after_publish(self, restaurant: Any, zone: Any) -> None:
        from unittest.mock import patch

        client = _admin_api(restaurant.id)
        zid = str(zone.public_id)

        # Save a draft
        client.put("/api/editor/layouts/draft/", _layout_a(zid), format="json")
        assert LayoutDraft.objects.count() == 1

        # Publish — this should delete the draft
        with patch("apps.editor.services.emit_hall_layout_published"):
            client.post("/api/editor/layouts/publish/", _layout_a(zid), format="json")

        assert LayoutDraft.objects.count() == 0

    def test_publish_only_deletes_current_admin_draft(self, restaurant: Any, zone: Any) -> None:
        from unittest.mock import patch

        first_admin, _ = _admin_api_with_user(restaurant.id)
        second_admin, _ = _admin_api_with_user(restaurant.id)
        payload = _layout_a(str(zone.public_id))

        first_admin.put("/api/editor/layouts/draft/", payload, format="json")
        second_admin.put("/api/editor/layouts/draft/", payload, format="json")

        with patch("apps.editor.services.emit_hall_layout_published"):
            response = first_admin.post("/api/editor/layouts/publish/", payload, format="json")

        assert response.status_code == 201
        assert LayoutDraft.objects.filter(restaurant=restaurant).count() == 1
        assert second_admin.get("/api/editor/layouts/draft/").json()["is_draft"] is True

    def test_draft_preserved_on_publish_failure(self, restaurant: Any, zone: Any) -> None:
        client = _admin_api(restaurant.id)

        # Save a draft
        client.put(
            "/api/editor/layouts/draft/",
            _layout_a(str(zone.public_id)),
            format="json",
        )

        # Try to publish invalid data — should fail
        response = client.post(
            "/api/editor/layouts/publish/",
            {"tables": [{"shape": "triangle"}]},
            format="json",
        )
        assert response.status_code == 400

        # Draft should still exist
        assert LayoutDraft.objects.count() == 1

    def test_publish_without_draft_still_works(self, restaurant: Any, zone: Any) -> None:
        """Publishing should work normally even when no draft exists."""
        from unittest.mock import patch

        client = _admin_api(restaurant.id)

        with patch("apps.editor.services.emit_hall_layout_published"):
            response = client.post(
                "/api/editor/layouts/publish/",
                _layout_a(str(zone.public_id)),
                format="json",
            )
        assert response.status_code == 201
        assert LayoutVersion.objects.count() == 1
