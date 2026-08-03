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
    Ingredient,
    MenuItem,
    MenuItemAllergen,
    MenuItemIngredient,
)
from apps.menu.services import prune_orphans
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
    return RestaurantSettingsFactory.create(restaurant=restaurant, locale="uk")


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


def _dish(
    restaurant: Restaurant,
    menu: Any,
    category: Any,
    name: str,
) -> MenuItem:
    return MenuItem.objects.create(
        restaurant=restaurant,
        menu=menu,
        category=category,
        name=name,
        price=Decimal("29.9900"),
    )


def _create_allergen(restaurant: Restaurant, name: str) -> Allergen:
    return Allergen.objects.create(restaurant=restaurant, name=name, sort_order=0)


def _create_ingredient(restaurant: Restaurant, name: str) -> Ingredient:
    return Ingredient.objects.create(restaurant=restaurant, name=name, sort_order=0)


def _link_allergen(item: MenuItem, allergen: Allergen) -> MenuItemAllergen:
    return MenuItemAllergen.objects.create(menu_item=item, allergen=allergen, sort_order=0)


def _link_ingredient(item: MenuItem, ingredient: Ingredient) -> MenuItemIngredient:
    return MenuItemIngredient.objects.create(menu_item=item, ingredient=ingredient, sort_order=0)


# --- US-6 AS1/AS3: removing the last reference deletes the entry ---


def test_prune_orphans_deletes_last_referenced_allergen(
    restaurant: Restaurant,
    menu: Any,
    category: Any,
) -> None:
    dish = _dish(restaurant, menu, category, "Dish A")
    allergen = _create_allergen(restaurant, "Gluten")
    link = _link_allergen(dish, allergen)

    link.delete()

    deleted = prune_orphans(
        entity_model=Allergen,
        through_model=MenuItemAllergen,
        removed_ids=[allergen.pk],
    )
    assert deleted == 1
    assert not Allergen.objects.filter(pk=allergen.pk).exists()


def test_prune_orphans_deletes_last_referenced_ingredient(
    restaurant: Restaurant,
    menu: Any,
    category: Any,
) -> None:
    dish = _dish(restaurant, menu, category, "Dish A")
    ingredient = _create_ingredient(restaurant, "Tomato")
    link = _link_ingredient(dish, ingredient)

    link.delete()

    deleted = prune_orphans(
        entity_model=Ingredient,
        through_model=MenuItemIngredient,
        removed_ids=[ingredient.pk],
    )
    assert deleted == 1
    assert not Ingredient.objects.filter(pk=ingredient.pk).exists()


# --- US-6 AS2: entry still referenced by another dish is kept ---


def test_prune_orphans_keeps_entry_still_referenced(
    restaurant: Restaurant,
    menu: Any,
    category: Any,
) -> None:
    dish_a = _dish(restaurant, menu, category, "Dish A")
    dish_b = _dish(restaurant, menu, category, "Dish B")
    allergen = _create_allergen(restaurant, "Gluten")
    _link_allergen(dish_a, allergen)
    _link_allergen(dish_b, allergen)

    deleted = prune_orphans(
        entity_model=Allergen,
        through_model=MenuItemAllergen,
        removed_ids=[allergen.pk],
    )
    assert deleted == 0
    assert Allergen.objects.filter(pk=allergen.pk).exists()


# --- API-level: update() wipes + prunes inside a transaction ---


def test_update_removing_last_allergen_reference_prunes_entry(
    admin: Callable[..., AuthContext],
    restaurant: Restaurant,
    menu: Any,
    category: Any,
) -> None:
    dish = _dish(restaurant, menu, category, "Dish A")
    allergen = _create_allergen(restaurant, "Gluten")
    _link_allergen(dish, allergen)

    ctx = admin()
    resp = ctx.client.patch(
        f"/api/menu/admin/items/{dish.public_id}/",
        {"allergens": []},
        format="json",
    )
    assert resp.status_code == 200
    assert not Allergen.objects.filter(pk=allergen.pk).exists()


def test_update_removing_one_of_two_references_keeps_entry(
    admin: Callable[..., AuthContext],
    restaurant: Restaurant,
    menu: Any,
    category: Any,
) -> None:
    dish_a = _dish(restaurant, menu, category, "Dish A")
    dish_b = _dish(restaurant, menu, category, "Dish B")
    allergen = _create_allergen(restaurant, "Gluten")
    _link_allergen(dish_a, allergen)
    _link_allergen(dish_b, allergen)

    ctx = admin()
    resp = ctx.client.patch(
        f"/api/menu/admin/items/{dish_a.public_id}/",
        {"allergens": []},
        format="json",
    )
    assert resp.status_code == 200
    assert Allergen.objects.filter(pk=allergen.pk).exists()


# --- US-6 AS4: dish deletion prunes entries referenced only by it ---


def test_dish_deletion_prunes_unreferenced_entries(
    admin: Callable[..., AuthContext],
    restaurant: Restaurant,
    menu: Any,
    category: Any,
) -> None:
    dish = _dish(restaurant, menu, category, "Dish A")
    allergen = _create_allergen(restaurant, "Gluten")
    ingredient = _create_ingredient(restaurant, "Tomato")
    _link_allergen(dish, allergen)
    _link_ingredient(dish, ingredient)

    ctx = admin()
    resp = ctx.client.delete(f"/api/menu/admin/items/{dish.public_id}/")
    assert resp.status_code == 204
    assert not Allergen.objects.filter(pk=allergen.pk).exists()
    assert not Ingredient.objects.filter(pk=ingredient.pk).exists()


def test_dish_deletion_preserves_entries_still_referenced(
    admin: Callable[..., AuthContext],
    restaurant: Restaurant,
    menu: Any,
    category: Any,
) -> None:
    dish_a = _dish(restaurant, menu, category, "Dish A")
    dish_b = _dish(restaurant, menu, category, "Dish B")
    allergen = _create_allergen(restaurant, "Gluten")
    _link_allergen(dish_a, allergen)
    _link_allergen(dish_b, allergen)

    ctx = admin()
    resp = ctx.client.delete(f"/api/menu/admin/items/{dish_a.public_id}/")
    assert resp.status_code == 204
    assert Allergen.objects.filter(pk=allergen.pk).exists()


def test_bulk_delete_prunes_unreferenced_entries(
    admin: Callable[..., AuthContext],
    restaurant: Restaurant,
    menu: Any,
    category: Any,
) -> None:
    dish = _dish(restaurant, menu, category, "Dish A")
    allergen = _create_allergen(restaurant, "Gluten")
    _link_allergen(dish, allergen)

    ctx = admin()
    resp = ctx.client.post(
        "/api/menu/admin/items/bulk/",
        {"ids": [str(dish.public_id)], "action": "delete"},
        format="json",
    )
    assert resp.status_code == 200
    assert not Allergen.objects.filter(pk=allergen.pk).exists()


# --- US-7 AS3: pruning is isolated per restaurant ---


def test_cross_restaurant_pruning_isolation(
    admin: Callable[..., AuthContext],
    restaurant: Restaurant,
    menu: Any,
    category: Any,
) -> None:
    other = RestaurantFactory(name="Other Restaurant")
    other_menu = MenuFactory(restaurant=other, name="Other Menu")
    other_category = MenuCategoryFactory(menu=other_menu, name="Mains", sort_order=1)

    dish_a = _dish(restaurant, menu, category, "Dish A")
    other_dish = _dish(other, other_menu, other_category, "Other Dish")
    allergen_a = _create_allergen(restaurant, "Gluten")
    allergen_b = _create_allergen(other, "Gluten")
    _link_allergen(dish_a, allergen_a)
    _link_allergen(other_dish, allergen_b)

    ctx = admin()
    resp = ctx.client.delete(f"/api/menu/admin/items/{dish_a.public_id}/")
    assert resp.status_code == 204
    assert not Allergen.objects.filter(pk=allergen_a.pk).exists()
    assert Allergen.objects.filter(pk=allergen_b.pk).exists()
