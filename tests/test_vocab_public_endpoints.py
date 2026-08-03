# mypy: disable-error-code="no-untyped-call"
import uuid
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.menu.models import Allergen, AllergenTranslation, Ingredient, IngredientTranslation
from apps.restaurants.models import Restaurant, RestaurantSettings

from .conftest import RestaurantFactory, RestaurantSettingsFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def restaurant_a() -> Restaurant:
    return RestaurantFactory(name="Restaurant A")


@pytest.fixture
def restaurant_b() -> Restaurant:
    return RestaurantFactory(name="Restaurant B")


@pytest.fixture
def settings_a(restaurant_a: Restaurant) -> RestaurantSettings:
    return RestaurantSettingsFactory.create(
        restaurant=restaurant_a,
        locale="uk",
        supported_languages=["uk", "en"],
    )


@pytest.fixture
def settings_b(restaurant_b: Restaurant) -> RestaurantSettings:
    return RestaurantSettingsFactory.create(
        restaurant=restaurant_b,
        locale="en",
        supported_languages=["uk", "en"],
    )


def _create_allergen(restaurant: Restaurant, *, name: str) -> Allergen:
    return Allergen.objects.create(restaurant=restaurant, name=name, sort_order=0)


def _create_ingredient(restaurant: Restaurant, *, name: str) -> Ingredient:
    return Ingredient.objects.create(restaurant=restaurant, name=name, sort_order=0)


# --- FR-024 / US-7: AllergenListView is restaurant-scoped [{public_id, name}] ---


def test_allergen_list_requires_restaurant_param() -> None:
    resp = APIClient().get("/api/menu/allergens/")
    assert resp.status_code == 404


def test_allergen_list_unknown_restaurant_returns_404() -> None:
    resp = APIClient().get(f"/api/menu/allergens/?restaurant={uuid.uuid4()}")
    assert resp.status_code == 404


def test_allergen_list_scoped_to_restaurant(
    restaurant_a: Restaurant,
    restaurant_b: Restaurant,
) -> None:
    allergen = _create_allergen(restaurant_a, name="Глютен")
    _create_allergen(restaurant_b, name="Gluten")

    resp = APIClient().get(f"/api/menu/allergens/?restaurant={restaurant_a.public_id}")
    assert resp.status_code == 200
    assert resp.json() == [{"public_id": str(allergen.public_id), "name": "Глютен"}]


def test_allergen_list_localized(
    restaurant_a: Restaurant,
    settings_a: RestaurantSettings,
) -> None:
    allergen = _create_allergen(restaurant_a, name="Глютен")
    AllergenTranslation.objects.create(allergen=allergen, language_code="en", name="Gluten")

    client = APIClient()
    url = f"/api/menu/allergens/?restaurant={restaurant_a.public_id}"

    # Default locale: falls back to entity.name.
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.json() == [{"public_id": str(allergen.public_id), "name": "Глютен"}]

    # English preference: localized display name.
    resp = client.get(url, HTTP_ACCEPT_LANGUAGE="en")
    assert resp.status_code == 200
    assert resp.json() == [{"public_id": str(allergen.public_id), "name": "Gluten"}]


# --- FR-024 / US-7: IngredientListView keeps the [{public_id, name}] shape ---


def test_ingredient_list_requires_restaurant_param() -> None:
    resp = APIClient().get("/api/menu/ingredients/")
    assert resp.status_code == 404


def test_ingredient_list_unknown_restaurant_returns_404() -> None:
    resp = APIClient().get(f"/api/menu/ingredients/?restaurant={uuid.uuid4()}")
    assert resp.status_code == 404


def test_ingredient_list_scoped_and_public_id_name_shape(
    restaurant_a: Restaurant,
    restaurant_b: Restaurant,
) -> None:
    ingredient = _create_ingredient(restaurant_a, name="Помідор")
    _create_ingredient(restaurant_b, name="Tomato")

    resp = APIClient().get(f"/api/menu/ingredients/?restaurant={restaurant_a.public_id}")
    assert resp.status_code == 200
    assert resp.json() == [{"public_id": str(ingredient.public_id), "name": "Помідор"}]


def test_ingredient_list_localized_fallback_to_entity_name(
    restaurant_a: Restaurant,
    settings_a: RestaurantSettings,
) -> None:
    ingredient = _create_ingredient(restaurant_a, name="Помідор")
    IngredientTranslation.objects.create(ingredient=ingredient, language_code="en", name="Tomato")

    client = APIClient()
    url = f"/api/menu/ingredients/?restaurant={restaurant_a.public_id}"

    resp = client.get(url, HTTP_ACCEPT_LANGUAGE="en")
    assert resp.status_code == 200
    assert resp.json() == [{"public_id": str(ingredient.public_id), "name": "Tomato"}]

    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.json() == [{"public_id": str(ingredient.public_id), "name": "Помідор"}]
