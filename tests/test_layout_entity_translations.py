from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.authentication.models import RoleCode
from apps.authentication.services import issue_tokens_with_restaurant
from apps.editor.models import LayoutEntityTranslation, LayoutVersion
from apps.restaurants.models import RestaurantSettings
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


def _client(role: str, restaurant_id: int) -> APIClient:
    user = UserFactory.build(role=role)
    user.save()
    client = _EditorAPIClient(restaurant_id)
    access, _ = issue_tokens_with_restaurant(user, restaurant_id)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _admin_client(restaurant_id: int) -> APIClient:
    return _client(RoleCode.ADMIN, restaurant_id)


def _layout(
    zone_id: str,
    threshold_label: str = "Threshold A",
    portal_label: str = "Portal B",
) -> dict[str, Any]:
    return {
        "thresholds": [
            {
                "x": 100,
                "y": 100,
                "width": 200,
                "height": 100,
                "zone_id": zone_id,
                "label": threshold_label,
            }
        ],
        "portals": [
            {
                "x": 300,
                "y": 100,
                "width": 200,
                "height": 100,
                "zone_id": zone_id,
                "target_zone_id": zone_id,
                "label": portal_label,
            }
        ],
    }


def _publish(client: APIClient, payload: dict[str, Any]) -> Any:
    with patch("apps.editor.services.emit_hall_layout_published"):
        return client.post("/api/editor/layouts/publish/", payload, format="json")


def _latest_version(restaurant_id: int) -> LayoutVersion:
    return (
        LayoutVersion.objects.filter(restaurant_id=restaurant_id)
        .order_by("-published_at", "-id")
        .first()
    )


def _entity_ids(version: LayoutVersion) -> dict[str, str]:
    return {
        "threshold": str(version.layout_json["thresholds"][0]["id"]),
        "portal": str(version.layout_json["portals"][0]["id"]),
    }


@pytest.mark.django_db
class TestEntityTranslationEndpoints:
    def test_list_empty_before_publish(self, restaurant: Any) -> None:
        client = _admin_client(restaurant.id)
        resp = client.get("/api/editor/layouts/entity-translations/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_list_update_delete_roundtrip(
        self, restaurant: Any, zone: Any, restaurant_settings: Any
    ) -> None:
        client = _admin_client(restaurant.id)
        resp = _publish(client, _layout(str(zone.public_id)))
        assert resp.status_code == 201, resp.json()
        version = _latest_version(restaurant.id)
        ids = _entity_ids(version)

        create_resp = client.post(
            "/api/editor/layouts/entity-translations/",
            {"entity_id": ids["threshold"], "language_code": "en", "label": "Зала А"},
            format="json",
        )
        assert create_resp.status_code == 201, create_resp.json()
        assert create_resp.json()["label"] == "Зала А"
        assert LayoutEntityTranslation.objects.filter(
            layout_version_id=version.pk, entity_id=ids["threshold"], language_code="en"
        ).exists()

        list_resp = client.get("/api/editor/layouts/entity-translations/")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1
        assert list_resp.json()[0]["entity_id"] == ids["threshold"]

        filtered = client.get("/api/editor/layouts/entity-translations/?language=en")
        assert len(filtered.json()) == 1
        filtered_uk = client.get("/api/editor/layouts/entity-translations/?language=uk")
        assert filtered_uk.json() == []

        update_resp = client.put(
            f"/api/editor/layouts/entity-translations/{ids['threshold']}/en/",
            {"current": {"label": "Зала А"}, "updated": {"label": "Зала A2"}},
            format="json",
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["label"] == "Зала A2"

        conflict_resp = client.put(
            f"/api/editor/layouts/entity-translations/{ids['threshold']}/en/",
            {"current": {"label": "Зала А"}, "updated": {"label": "Stale"}},
            format="json",
        )
        assert conflict_resp.status_code == 409
        assert LayoutEntityTranslation.objects.get(
            layout_version_id=version.pk, entity_id=ids["threshold"], language_code="en"
        ).label == "Зала A2"

        del_resp = client.delete(
            f"/api/editor/layouts/entity-translations/{ids['threshold']}/en/"
        )
        assert del_resp.status_code == 204
        assert (
            LayoutEntityTranslation.objects.filter(
                layout_version_id=version.pk, entity_id=ids["threshold"], language_code="en"
            ).count()
            == 0
        )

    def test_unknown_entity_rejected(
        self, restaurant: Any, zone: Any, restaurant_settings: Any
    ) -> None:
        client = _admin_client(restaurant.id)
        _publish(client, _layout(str(zone.public_id)))
        unknown = "00000000-0000-0000-0000-000000000001"
        resp = client.post(
            "/api/editor/layouts/entity-translations/",
            {"entity_id": unknown, "language_code": "en", "label": "X"},
            format="json",
        )
        assert resp.status_code == 400
        assert "does not exist" in resp.json()["detail"]

    def test_default_language_rejected(
        self, restaurant: Any, zone: Any, restaurant_settings: Any
    ) -> None:
        assert restaurant_settings.locale == "uk"
        client = _admin_client(restaurant.id)
        _publish(client, _layout(str(zone.public_id)))
        ids = _entity_ids(_latest_version(restaurant.id))
        resp = client.post(
            "/api/editor/layouts/entity-translations/",
            {"entity_id": ids["threshold"], "language_code": "uk", "label": "X"},
            format="json",
        )
        assert resp.status_code == 400
        assert "primary language" in resp.json()["detail"]

    def test_duplicate_create_rejected(
        self, restaurant: Any, zone: Any, restaurant_settings: Any
    ) -> None:
        client = _admin_client(restaurant.id)
        _publish(client, _layout(str(zone.public_id)))
        ids = _entity_ids(_latest_version(restaurant.id))
        payload = {"entity_id": ids["threshold"], "language_code": "en", "label": "Зала А"}
        assert client.post("/api/editor/layouts/entity-translations/", payload, format="json").status_code == 201
        duplicate = client.post("/api/editor/layouts/entity-translations/", payload, format="json")
        assert duplicate.status_code == 400

    def test_non_admin_forbidden(
        self, restaurant: Any, zone: Any, restaurant_settings: Any
    ) -> None:
        _publish(_admin_client(restaurant.id), _layout(str(zone.public_id)))
        waiter = _client(RoleCode.WAITER, restaurant.id)
        resp = waiter.get("/api/editor/layouts/entity-translations/")
        assert resp.status_code == 403

    def test_invalid_entity_id_in_url_rejected(
        self, restaurant: Any, zone: Any, restaurant_settings: Any
    ) -> None:
        client = _admin_client(restaurant.id)
        _publish(client, _layout(str(zone.public_id)))
        resp = client.put(
            "/api/editor/layouts/entity-translations/not-a-uuid/en/",
            {"current": {}, "updated": {"label": "X"}},
            format="json",
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestCopyForward:
    def test_translations_survive_republish_for_surviving_entities(
        self, restaurant: Any, zone: Any, restaurant_settings: Any
    ) -> None:
        client = _admin_client(restaurant.id)
        _publish(client, _layout(str(zone.public_id)))
        v1 = _latest_version(restaurant.id)
        ids = _entity_ids(v1)

        client.post(
            "/api/editor/layouts/entity-translations/",
            {"entity_id": ids["threshold"], "language_code": "en", "label": "Зала А"},
            format="json",
        )
        client.post(
            "/api/editor/layouts/entity-translations/",
            {"entity_id": ids["portal"], "language_code": "en", "label": "Вихід"},
            format="json",
        )

        layout2 = _layout(str(zone.public_id))
        layout2["thresholds"][0]["id"] = ids["threshold"]
        layout2["portals"][0]["id"] = ids["portal"]
        republish = _publish(client, layout2)
        assert republish.status_code == 201, republish.json()

        v2 = _latest_version(restaurant.id)
        assert v2.parent_version_id == v1.pk
        assert LayoutEntityTranslation.objects.filter(layout_version_id=v2.pk).count() == 2
        assert LayoutEntityTranslation.objects.filter(
            layout_version_id=v2.pk, entity_id=ids["threshold"], language_code="en", label="Зала А"
        ).exists()

    def test_translations_dropped_for_removed_entities(
        self, restaurant: Any, zone: Any, restaurant_settings: Any
    ) -> None:
        client = _admin_client(restaurant.id)
        _publish(client, _layout(str(zone.public_id)))
        v1 = _latest_version(restaurant.id)
        ids = _entity_ids(v1)
        client.post(
            "/api/editor/layouts/entity-translations/",
            {"entity_id": ids["portal"], "language_code": "en", "label": "Вихід"},
            format="json",
        )
        assert LayoutEntityTranslation.objects.filter(layout_version_id=v1.pk).count() == 1

        layout2 = _layout(str(zone.public_id))
        layout2["thresholds"][0]["id"] = ids["threshold"]
        layout2["portals"] = []
        _publish(client, layout2)

        v2 = _latest_version(restaurant.id)
        assert LayoutEntityTranslation.objects.filter(layout_version_id=v2.pk).count() == 0

    def test_fresh_thresholds_gain_stable_ids_on_publish(
        self, restaurant: Any, zone: Any
    ) -> None:
        client = _admin_client(restaurant.id)
        resp = _publish(client, _layout(str(zone.public_id)))
        assert resp.status_code == 201
        version = _latest_version(restaurant.id)
        ids = _entity_ids(version)
        assert ids["threshold"]
        assert ids["portal"]
        assert LayoutEntityTranslation.objects.filter(layout_version_id=version.pk).count() == 0


@pytest.mark.django_db
class TestReadLocalization:
    def _publish_with_settings(self, restaurant: Any, zone: Any) -> Any:
        RestaurantSettings.objects.create(
            restaurant=restaurant,
            locale="uk",
            currency="UAH",
            supported_languages=["uk", "en"],
        )
        client = _admin_client(restaurant.id)
        _publish(client, _layout(str(zone.public_id)))
        ids = _entity_ids(_latest_version(restaurant.id))
        client.post(
            "/api/editor/layouts/entity-translations/",
            {"entity_id": ids["threshold"], "language_code": "en", "label": "Зала А"},
            format="json",
        )
        return client

    def test_floor_plan_layout_localizes_non_default_language(
        self, restaurant: Any, zone: Any
    ) -> None:
        self._publish_with_settings(restaurant, zone)
        anon = APIClient()
        resp = anon.get(
            f"/api/restaurants/tables/layout/?restaurant={restaurant.public_id}",
            HTTP_ACCEPT_LANGUAGE="en",
        )
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        threshold = data["layout"]["thresholds"][0]
        assert threshold["label"] == "Зала А"
        portal = data["layout"]["portals"][0]
        assert portal["label"] == "Portal B"

    def test_floor_plan_layout_default_language_keeps_default_labels(
        self, restaurant: Any, zone: Any
    ) -> None:
        self._publish_with_settings(restaurant, zone)
        anon = APIClient()
        resp = anon.get(
            f"/api/restaurants/tables/layout/?restaurant={restaurant.public_id}",
            HTTP_ACCEPT_LANGUAGE="uk",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["layout"]["thresholds"][0]["label"] == "Threshold A"
        assert data["layout"]["portals"][0]["label"] == "Portal B"

    def test_editor_latest_returns_layout_with_stable_ids(self, restaurant: Any, zone: Any) -> None:
        client = self._publish_with_settings(restaurant, zone)
        resp = client.get("/api/editor/layouts/latest/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["layout_json"]["thresholds"][0]["id"]
        assert data["layout_json"]["portals"][0]["id"]
        assert "label" in data["layout_json"]["thresholds"][0]
        assert "label" in data["layout_json"]["portals"][0]


@pytest.mark.django_db
class TestStableIdsLegacyLabels:
    def test_legacy_threshold_label_portal_label_accepted_on_publish(
        self, restaurant: Any, zone: Any
    ) -> None:
        client = _admin_client(restaurant.id)
        payload = {
            "thresholds": [
                {
                    "x": 100,
                    "y": 100,
                    "width": 200,
                    "height": 100,
                    "zone_id": str(zone.public_id),
                    "threshold_label": "Old Threshold",
                }
            ],
            "portals": [
                {
                    "x": 300,
                    "y": 100,
                    "width": 200,
                    "height": 100,
                    "zone_id": str(zone.public_id),
                    "target_zone_id": str(zone.public_id),
                    "portal_label": "Old Portal",
                }
            ],
        }
        resp = _publish(client, payload)
        assert resp.status_code == 201, resp.json()
        version = _latest_version(restaurant.id)
        assert version.layout_json["thresholds"][0]["label"] == "Old Threshold"
        assert version.layout_json["portals"][0]["label"] == "Old Portal"
