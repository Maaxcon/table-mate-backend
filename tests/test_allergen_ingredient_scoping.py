# mypy: disable-error-code="no-untyped-call"
from collections.abc import Callable
from typing import Any

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.authentication.models import RoleCode
from apps.authentication.services import issue_tokens_with_restaurant
from apps.menu.models import (
    Allergen,
    AllergenTranslation,
    Ingredient,
    IngredientTranslation,
    Menu,
    MenuCategory,
    MenuItem,
    MenuItemAllergen,
    MenuItemIngredient,
)
from apps.menu.services import (
    create_allergen_translation,
    create_ingredient_translation,
    update_allergen_translation,
    update_ingredient_translation,
)
from apps.menu.services.localization import get_restaurant_locale
from apps.restaurants.models import Restaurant, RestaurantSettings

from .conftest import (
    AuthContext,
    RestaurantFactory,
    RestaurantSettingsFactory,
    UserFactory,
)


@pytest.fixture
def restaurant_a() -> Restaurant:
    return RestaurantFactory(name="Restaurant A")


@pytest.fixture
def restaurant_b() -> Restaurant:
    return RestaurantFactory(name="Restaurant B")


@pytest.fixture
def settings_a(restaurant_a: Restaurant) -> RestaurantSettings:
    return RestaurantSettingsFactory.create(restaurant=restaurant_a, locale="uk", supported_languages=["uk", "en"])


@pytest.fixture
def settings_b(restaurant_b: Restaurant) -> RestaurantSettings:
    return RestaurantSettingsFactory.create(restaurant=restaurant_b, locale="en", supported_languages=["uk", "en"])


@pytest.fixture
def admin_a(restaurant_a: Restaurant) -> Callable[..., AuthContext]:
    def _auth() -> AuthContext:
        user = UserFactory.build(role=RoleCode.ADMIN)
        user.save()
        client = APIClient()
        access, _ = issue_tokens_with_restaurant(user, restaurant_a.pk)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        return AuthContext(client=client, user=user)

    return _auth


@pytest.fixture
def admin_b(restaurant_b: Restaurant) -> Callable[..., AuthContext]:
    def _auth() -> AuthContext:
        user = UserFactory.build(role=RoleCode.ADMIN)
        user.save()
        client = APIClient()
        access, _ = issue_tokens_with_restaurant(user, restaurant_b.pk)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        return AuthContext(client=client, user=user)

    return _auth


def _create_vocab_entry(
    restaurant: Restaurant,
    *,
    model: type[Allergen | Ingredient],
    key: str,
    name: str,
) -> Allergen | Ingredient:
    return model.objects.create(restaurant=restaurant, key=key, name=name, sort_order=0)


# --- US-8: name stored on the entity, translations hold non-default languages ---


@pytest.mark.django_db
def test_name_lives_on_entity_and_translation_stored_separately(restaurant_a: Restaurant, settings_a: Any) -> None:
    allergen = _create_vocab_entry(restaurant_a, model=Allergen, key="gluten", name="Глютен")
    AllergenTranslation.objects.create(allergen=allergen, language_code="en", name="Gluten")

    allergen.refresh_from_db()
    assert allergen.name == "Глютен"
    assert AllergenTranslation.objects.filter(allergen=allergen, language_code="en", name="Gluten").exists()


@pytest.mark.django_db
def test_default_locale_translation_create_rejected(restaurant_a: Restaurant, settings_a: Any) -> None:
    allergen = _create_vocab_entry(restaurant_a, model=Allergen, key="gluten", name="Глютен")
    locale = get_restaurant_locale(restaurant_a.pk)
    assert locale == "uk"

    with pytest.raises(ValidationError):
        create_allergen_translation(
            allergen_public_id=str(allergen.public_id),
            restaurant_id=restaurant_a.pk,
            language_code=locale,
            name="Глютен",
        )


@pytest.mark.django_db
def test_default_locale_translation_update_rejected(restaurant_a: Restaurant, settings_a: Any) -> None:
    allergen = _create_vocab_entry(restaurant_a, model=Allergen, key="gluten", name="Глютен")
    AllergenTranslation.objects.create(allergen=allergen, language_code="en", name="Gluten")
    locale = get_restaurant_locale(restaurant_a.pk)

    with pytest.raises(ValidationError):
        update_allergen_translation(
            allergen_public_id=str(allergen.public_id),
            restaurant_id=restaurant_a.pk,
            language_code=locale,
            name="Updated",
        )


@pytest.mark.django_db
def test_default_locale_ingredient_translation_rejected(restaurant_a: Restaurant, settings_a: Any) -> None:
    ingredient = _create_vocab_entry(restaurant_a, model=Ingredient, key="tomato", name="Помідор")

    with pytest.raises(ValidationError):
        create_ingredient_translation(ingredient_id=ingredient.pk, language_code="uk", name="Помідор")


@pytest.mark.django_db
def test_ingredient_name_stored_on_entity(restaurant_a: Restaurant, settings_a: Any) -> None:
    ingredient = _create_vocab_entry(restaurant_a, model=Ingredient, key="tomato", name="Помідор")
    IngredientTranslation.objects.create(ingredient=ingredient, language_code="en", name="Tomato")

    ingredient.refresh_from_db()
    assert ingredient.name == "Помідор"
    assert IngredientTranslation.objects.filter(ingredient=ingredient, language_code="en", name="Tomato").exists()


# --- US-7: per-restaurant allergen independence + admin list scoping ---


@pytest.mark.django_db
def test_allergens_are_restaurant_scoped(restaurant_a: Restaurant, restaurant_b: Restaurant) -> None:
    a = _create_vocab_entry(restaurant_a, model=Allergen, key="gluten", name="Глютен")
    b = _create_vocab_entry(restaurant_b, model=Allergen, key="gluten", name="Gluten")

    assert a.pk != b.pk
    assert Allergen.objects.filter(key="gluten").count() == 2
    assert list(Allergen.objects.filter(restaurant_id=restaurant_a.pk)) == [a]
    assert list(Allergen.objects.filter(restaurant_id=restaurant_b.pk)) == [b]


@pytest.mark.django_db
def test_admin_list_is_scoped_to_own_restaurant(admin_a: Callable[..., AuthContext], restaurant_a: Restaurant, restaurant_b: Restaurant) -> None:
    _create_vocab_entry(restaurant_a, model=Allergen, key="gluten", name="Глютен")
    _create_vocab_entry(restaurant_b, model=Allergen, key="gluten", name="Gluten")

    ctx = admin_a()
    response = ctx.client.get("/api/menu/admin/allergens/")
    assert response.status_code == 200
    results = response.data["results"]
    assert len(results) == 1
    assert results[0]["key"] == "gluten"


@pytest.mark.django_db
def test_admin_allergen_translation_scoped(
    admin_a: Callable[..., AuthContext],
    restaurant_a: Restaurant,
    restaurant_b: Restaurant,
    settings_a: Any,
) -> None:
    mine = _create_vocab_entry(restaurant_a, model=Allergen, key="gluten", name="Глютен")
    other = _create_vocab_entry(restaurant_b, model=Allergen, key="gluten", name="Gluten")

    ctx = admin_a()
    response = ctx.client.post(
        f"/api/menu/admin/allergens/{mine.public_id}/translations/",
        {"language_code": "en", "name": "Gluten"},
        format="json",
    )
    assert response.status_code == 201

    # A translation for another restaurant's allergen is not reachable.
    response = ctx.client.get(f"/api/menu/admin/allergens/{other.public_id}/")
    assert response.status_code == 404


# --- Data migration backfill correctness ---


@pytest.mark.django_db(transaction=True)
def test_backfill_migration_preserves_default_locale_name() -> None:
    executor = MigrationExecutor(connection)
    from django.db.migrations.recorder import MigrationRecorder

    executor.migrate([("menu", "0022_allergen_public_id")])
    old_state = executor.loader.project_state([("menu", "0022_allergen_public_id")])

    RestaurantModel = old_state.apps.get_model("restaurants", "Restaurant")
    RestaurantSettingsModel = old_state.apps.get_model("restaurants", "RestaurantSettings")
    MenuModel = old_state.apps.get_model("menu", "Menu")
    AllergenModel = old_state.apps.get_model("menu", "Allergen")
    AllergenTranslationModel = old_state.apps.get_model("menu", "AllergenTranslation")
    MenuItemModel = old_state.apps.get_model("menu", "MenuItem")
    MenuItemAllergenModel = old_state.apps.get_model("menu", "MenuItemAllergen")

    restaurant = RestaurantModel.objects.create(name="Legacy Restaurant", address="X")
    RestaurantSettingsModel.objects.create(restaurant=restaurant, locale="uk")
    allergen = AllergenModel.objects.create(key="gluten", sort_order=0)
    AllergenTranslationModel.objects.create(allergen=allergen, language_code="uk", name="Глютен")
    AllergenTranslationModel.objects.create(allergen=allergen, language_code="en", name="Gluten")
    menu = MenuModel.objects.create(restaurant=restaurant, name="Legacy Menu")
    dish = MenuItemModel.objects.create(
        restaurant=restaurant,
        menu=menu,
        name="Dish",
        price="10.0000",
    )
    MenuItemAllergenModel.objects.create(menu_item=dish, allergen=allergen)

    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate([("menu", "0025_allergen_ingredient_finalize_not_null")])

    new_models = executor.loader.project_state([("menu", "0025_allergen_ingredient_finalize_not_null")]).apps
    AllergenNew = new_models.get_model("menu", "Allergen")
    AllergenTranslationNew = new_models.get_model("menu", "AllergenTranslation")
    MenuItemAllergenNew = new_models.get_model("menu", "MenuItemAllergen")

    scoped = AllergenNew.objects.filter(restaurant_id=restaurant.pk).first()
    assert scoped is not None
    assert scoped.name == "Глютен"
    assert not AllergenTranslationNew.objects.filter(
        allergen_id=scoped.pk, language_code="uk"
    ).exists()
    assert AllergenNew.objects.filter(restaurant__isnull=True).count() == 0
    assert MenuItemAllergenNew.objects.get().allergen_id == scoped.pk


@pytest.mark.django_db
def test_admin_api_creates_name_on_entity(admin_a: Callable[..., AuthContext], restaurant_a: Restaurant, settings_a: Any) -> None:
    ctx = admin_a()
    response = ctx.client.post(
        "/api/menu/admin/allergens/",
        {"key": "mustard", "name": "Гірчиця", "sort_order": 0},
        format="json",
    )
    assert response.status_code == 201
    allergen = Allergen.objects.get(public_id=response.data["public_id"])
    assert allergen.restaurant_id == restaurant_a.pk
    assert allergen.name == "Гірчиця"
