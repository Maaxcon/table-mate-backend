# mypy: disable-error-code="no-untyped-call"
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.authentication.models import RoleCode
from apps.authentication.services import issue_tokens_with_restaurant
from apps.menu.models import (
    Allergen,
    AllergenTranslation,
    Ingredient,
    IngredientTranslation,
    MenuItem,
    MenuItemAllergen,
    MenuItemIngredient,
)
from apps.restaurants.models import Restaurant, RestaurantSettings

from .conftest import (
    AuthContext,
    MenuCategoryFactory,
    MenuFactory,
    RestaurantFactory,
    RestaurantSettingsFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def restaurant() -> Restaurant:
    return RestaurantFactory(name="Test Restaurant")


@pytest.fixture
def settings(restaurant: Restaurant) -> RestaurantSettings:
    return RestaurantSettingsFactory.create(
        restaurant=restaurant,
        locale="uk",
        supported_languages=["uk", "en"],
    )


@pytest.fixture
def menu(restaurant: Restaurant) -> Any:
    return MenuFactory(restaurant=restaurant, name="Dinner")


@pytest.fixture
def category(menu: Any) -> Any:
    return MenuCategoryFactory(menu=menu, name="Mains", sort_order=1)


@pytest.fixture
def admin(restaurant: Restaurant) -> Callable[..., AuthContext]:
    def _auth() -> AuthContext:
        user = UserFactory.build(role=RoleCode.ADMIN)
        user.save()
        client = APIClient()
        access, _ = issue_tokens_with_restaurant(user, restaurant.pk)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        return AuthContext(client=client, user=user)

    return _auth


def _item_payload(menu: Any, category: Any, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "menu": str(menu.public_id),
        "category": str(category.public_id),
        "name": "Салат",
        "description": "Опис страви",
        "price": "29.9900",
        "ingredients": ["Помідор"],
        "allergens": ["Глютен"],
    }
    payload.update(overrides)
    return payload


# --- US-5 AS1: typing a new name creates the vocabulary entry ---


def test_create_dish_with_new_typed_names_creates_vocab_entries(
    admin: Callable[..., AuthContext],
    restaurant: Restaurant,
    menu: Any,
    category: Any,
) -> None:
    ctx = admin()
    resp = ctx.client.post("/api/menu/admin/items/", _item_payload(menu, category), format="json")
    assert resp.status_code == 201

    item = MenuItem.objects.get(public_id=resp.data["public_id"])
    assert list(item.allergens.values_list("name", flat=True)) == ["Глютен"]
    assert list(item.ingredients.values_list("name", flat=True)) == ["Помідор"]

    allergen = Allergen.objects.get(restaurant=restaurant, name="Глютен")
    ingredient = Ingredient.objects.get(restaurant=restaurant, name="Помідор")
    assert allergen.restaurant_id == restaurant.pk
    assert ingredient.restaurant_id == restaurant.pk


# --- US-5 AS4: names differing only in case/whitespace reuse the entry ---


def test_typed_name_case_and_whitespace_insensitive_reuse(
    admin: Callable[..., AuthContext],
    restaurant: Restaurant,
    menu: Any,
    category: Any,
) -> None:
    ctx = admin()
    resp = ctx.client.post(
        "/api/menu/admin/items/",
        _item_payload(menu, category, allergens=["Gluten"], ingredients=["Tomato"]),
        format="json",
    )
    assert resp.status_code == 201
    first_item = MenuItem.objects.get(public_id=resp.data["public_id"])
    allergen = first_item.allergens.get()
    ingredient = first_item.ingredients.get()

    resp2 = ctx.client.post(
        "/api/menu/admin/items/",
        _item_payload(
            menu,
            category,
            name="Салат 2",
            allergens=["  gluten  "],
            ingredients=[" tomato "],
        ),
        format="json",
    )
    assert resp2.status_code == 201
    second_item = MenuItem.objects.get(public_id=resp2.data["public_id"])

    assert list(second_item.allergens.values_list("pk", flat=True)) == [allergen.pk]
    assert list(second_item.ingredients.values_list("pk", flat=True)) == [ingredient.pk]
    assert Allergen.objects.filter(restaurant=restaurant, name__iexact="gluten").count() == 1
    assert Ingredient.objects.filter(restaurant=restaurant, name__iexact="tomato").count() == 1


def test_update_dish_with_known_name_reuses_existing_entry(
    admin: Callable[..., AuthContext],
    restaurant: Restaurant,
    menu: Any,
    category: Any,
) -> None:
    ctx = admin()
    created = ctx.client.post(
        "/api/menu/admin/items/",
        _item_payload(menu, category, allergens=["Gluten"]),
        format="json",
    )
    item = MenuItem.objects.get(public_id=created.data["public_id"])
    allergen = item.allergens.get()

    resp = ctx.client.patch(
        f"/api/menu/admin/items/{item.public_id}/",
        {"allergens": ["GLUTEN"]},
        format="json",
    )
    assert resp.status_code == 200
    item.refresh_from_db()
    assert list(item.allergens.values_list("pk", flat=True)) == [allergen.pk]
    assert Allergen.objects.filter(restaurant=restaurant).count() == 1


# --- US-5 AS3 / FR-020: admin read returns display names, never keys ---


def test_admin_item_read_returns_display_names(
    admin: Callable[..., AuthContext],
    menu: Any,
    category: Any,
) -> None:
    ctx = admin()
    created = ctx.client.post("/api/menu/admin/items/", _item_payload(menu, category), format="json")
    assert created.status_code == 201

    resp = ctx.client.get(f"/api/menu/admin/items/{created.data['public_id']}/")
    assert resp.status_code == 200
    assert resp.data["allergens"] == ["Глютен"]
    assert resp.data["ingredients"] == ["Помідор"]


# --- T051 / FR-021: public MenuItemSerializer localized-name fallback ---


def test_public_item_serializer_localizes_vocab_names(
    restaurant: Restaurant,
    settings: RestaurantSettings,
    menu: Any,
    category: Any,
) -> None:
    allergen = Allergen.objects.create(restaurant=restaurant, key="gluten", name="Глютен", sort_order=0)
    AllergenTranslation.objects.create(allergen=allergen, language_code="en", name="Gluten")
    ingredient = Ingredient.objects.create(restaurant=restaurant, key="tomato", name="Помідор", sort_order=0)
    IngredientTranslation.objects.create(ingredient=ingredient, language_code="en", name="Tomato")
    item = MenuItem.objects.create(
        restaurant=restaurant,
        menu=menu,
        category=category,
        name="Салат",
        price=Decimal("29.9900"),
    )
    MenuItemAllergen.objects.create(menu_item=item, allergen=allergen, sort_order=0)
    MenuItemIngredient.objects.create(menu_item=item, ingredient=ingredient, sort_order=0)

    client = APIClient()
    url = f"/api/menu/items/?restaurant={restaurant.public_id}"

    # Default locale (uk): falls back to entity.name.
    resp = client.get(url)
    assert resp.status_code == 200
    payload = resp.data["results"][0]
    assert payload["allergens"] == ["Глютен"]
    assert payload["ingredients"] == ["Помідор"]

    # English preference: localized names from translations.
    resp = client.get(url, HTTP_ACCEPT_LANGUAGE="en")
    assert resp.status_code == 200
    payload = resp.data["results"][0]
    assert payload["allergens"] == ["Gluten"]
    assert payload["ingredients"] == ["Tomato"]
