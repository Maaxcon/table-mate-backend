from typing import Any

import pytest

from apps.authentication.models import RoleCode

pytestmark = [pytest.mark.django_db]


def test_admin_can_create_restaurant_translation(api: Any, restaurant: Any, restaurant_settings: Any) -> None:
    client, _ = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
    resp = client.post(
        f"/api/restaurants/restaurants/{restaurant.public_id}/translations/",
        {"language_code": "en", "address": "123 Translated St"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["language_code"] == "en"
    assert resp.data["address"] == "123 Translated St"


def test_cannot_create_translation_for_primary_language(api: Any, restaurant: Any, restaurant_settings: Any) -> None:
    client, _ = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
    resp = client.post(
        f"/api/restaurants/restaurants/{restaurant.public_id}/translations/",
        {"language_code": restaurant_settings.locale, "address": "No"},
        format="json",
    )
    assert resp.status_code == 400


def test_admin_can_update_and_delete_restaurant_translation(
    api: Any, restaurant: Any, restaurant_settings: Any
) -> None:
    client, _ = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
    base = f"/api/restaurants/restaurants/{restaurant.public_id}/translations"

    created = client.post(base + "/", {"language_code": "en", "address": "Old"}, format="json")
    assert created.status_code == 201

    updated = client.put(
        base + "/en/",
        {"address": "New", "current": {"language_code": "en", "address": "Old"}},
        format="json",
    )
    assert updated.status_code == 200, updated.data
    assert updated.data["address"] == "New"

    listed = client.get(base + "/")
    assert listed.status_code == 200
    assert [t["language_code"] for t in listed.data] == ["en"]

    deleted = client.delete(base + "/en/")
    assert deleted.status_code == 204

    listed_after = client.get(base + "/")
    assert listed_after.data == []


def test_non_admin_cannot_create_restaurant_translation(api: Any, restaurant: Any, restaurant_settings: Any) -> None:
    client, _ = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
    resp = client.post(
        f"/api/restaurants/restaurants/{restaurant.public_id}/translations/",
        {"language_code": "en", "address": "No"},
        format="json",
    )
    assert resp.status_code == 403
