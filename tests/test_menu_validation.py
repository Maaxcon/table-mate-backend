from collections.abc import Callable
from decimal import Decimal
from typing import cast

import pytest
from django.core.exceptions import ValidationError

from apps.menu.models import Allergen, Menu, MenuCategory, MenuItem

from .conftest import MenuCategoryFactory as _MenuCategoryFactory
from .conftest import MenuFactory as _MenuFactory

MenuFactory = cast(Callable[..., Menu], _MenuFactory)
MenuCategoryFactory = cast(Callable[..., MenuCategory], _MenuCategoryFactory)


@pytest.mark.django_db
def test_clean_rejects_category_from_another_menu() -> None:
    menu = MenuFactory()
    other_category = MenuCategoryFactory()  # belongs to its own (different) menu

    item = MenuItem(
        restaurant=menu.restaurant,
        menu=menu,
        category=other_category,
        name="Steak",
        price=Decimal("29.9900"),
    )

    with pytest.raises(ValidationError) as exc:
        item.full_clean()
    assert "category" in exc.value.message_dict


@pytest.mark.django_db
def test_clean_allows_category_from_same_menu() -> None:
    menu = MenuFactory()
    category = MenuCategoryFactory(menu=menu)

    item = MenuItem(
        restaurant=menu.restaurant,
        menu=menu,
        category=category,
        name="Steak",
        price=Decimal("29.9900"),
    )

    item.full_clean()  # must not raise


@pytest.mark.django_db
def test_clean_allows_no_category() -> None:
    menu = MenuFactory()

    item = MenuItem(
        restaurant=menu.restaurant,
        menu=menu,
        category=None,
        name="Steak",
        price=Decimal("29.9900"),
    )

    item.full_clean()  # must not raise


@pytest.mark.django_db
def test_allergens_must_exist_in_catalog() -> None:
    menu = MenuFactory()
    item = MenuItem(
        restaurant=menu.restaurant,
        menu=menu,
        name="Steak",
        price=Decimal("29.9900"),
        allergens=["Custom allergen"],
    )

    with pytest.raises(ValidationError, match="Unknown allergens"):
        item.full_clean()

    Allergen.objects.create(name="Custom allergen")
    item.full_clean()
