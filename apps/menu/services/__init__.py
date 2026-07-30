from __future__ import annotations

import os
from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max, QuerySet
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from ..models import (
    Allergen,
    AllergenTranslation,
    Ingredient,
    IngredientTranslation,
    Menu,
    MenuCategory,
    MenuCategoryTranslation,
    MenuItem,
    MenuItemAllergen,
    MenuItemIngredient,
    MenuItemTranslation,
    MenuTranslation,
)
from ..selectors import get_default_upsell_items, get_upsell_suggestions


def reorder(queryset: QuerySet[Any], entries: list[dict[str, Any]]) -> None:
    """Apply a list of {public_id, sort_order} to a (restaurant-scoped) queryset
    in one atomic bulk update. Unknown/foreign ids are ignored. Works for both
    categories and items."""
    objs_by_id = {obj.public_id: obj for obj in queryset.filter(public_id__in=[e["public_id"] for e in entries])}
    # bulk_update bypasses save(), so refresh updated_at by hand.
    now = timezone.now()
    to_update: list[Any] = []
    for entry in entries:
        obj = objs_by_id.get(entry["public_id"])
        if obj is not None and obj.sort_order != entry["sort_order"]:
            obj.sort_order = entry["sort_order"]
            obj.updated_at = now
            to_update.append(obj)

    if to_update:
        with transaction.atomic():
            type(to_update[0]).objects.bulk_update(to_update, ["sort_order", "updated_at"])


def bulk_update_items(*, restaurant_id: int, data: dict[str, Any]) -> dict[str, int]:
    """Hide/show, set the category of, or delete several dishes at once. Only the
    restaurant's own items are touched; unknown ids are ignored."""
    items = MenuItem.objects.filter(restaurant_id=restaurant_id, public_id__in=data["ids"])

    if data["action"] == "delete":
        # Count up front: delete() returns cascaded rows too (e.g. likes).
        count = items.count()
        items.delete()
        return {"deleted": count}

    # update() bypasses save(), so set updated_at explicitly to keep it fresh.
    if data["action"] == "set_available":
        return {"updated": items.update(is_available=data["is_available"], updated_at=timezone.now())}

    # set_category: resolve a restaurant-owned category (or null to clear).
    category = None
    if data.get("category") is not None:
        category = MenuCategory.objects.filter(public_id=data["category"], menu__restaurant_id=restaurant_id).first()
        if category is None:
            raise serializers.ValidationError({"category": "Category not found."})
        # A category can only hold dishes from its own menu.
        if items.exclude(menu_id=category.menu_id).exists():
            raise serializers.ValidationError({"category": "Category must belong to the items' menu."})
    return {"updated": items.update(category=category, updated_at=timezone.now())}


def duplicate_item(item: MenuItem) -> MenuItem:
    """Server-side copy of a dish, including its image file."""
    # Place the copy at the end of its menu so it gets a unique sort_order
    # instead of tying with the source.
    max_order = MenuItem.objects.filter(menu=item.menu).aggregate(m=Max("sort_order"))["m"]
    copy = MenuItem(
        restaurant=item.restaurant,
        menu=item.menu,
        category=item.category,
        name=_unique_copy_name(item.menu, item.name),
        description=item.description,
        weight_grams=item.weight_grams,
        price=item.price,
        is_available=item.is_available,
        sort_order=(max_order or 0) + 1,
    )
    if item.image and item.image.name:
        filename = os.path.basename(item.image.name)
        item.image.open("rb")
        try:
            copy.image.save(
                filename,
                ContentFile(item.image.read()),
                save=False,
            )
        finally:
            item.image.close()
    copy.save()
    for thru in item.item_ingredients.all():
        MenuItemIngredient.objects.create(
            menu_item=copy,
            ingredient=thru.ingredient,
            sort_order=thru.sort_order,
        )
    for athru in item.item_allergens.all():
        MenuItemAllergen.objects.create(
            menu_item=copy,
            allergen=athru.allergen,
            sort_order=athru.sort_order,
        )
    for t in MenuItemTranslation.objects.filter(menu_item=item):
        MenuItemTranslation.objects.create(
            menu_item=copy,
            language_code=t.language_code,
            name=t.name,
            description=t.description,
        )
    return copy


def create_menu_translation(*, menu_id: int, language_code: str, name: str) -> MenuTranslation:
    return MenuTranslation.objects.create(
        menu_id=menu_id,
        language_code=language_code,
        name=name,
    )


def update_menu_translation(*, menu_id: int, language_code: str, name: str) -> MenuTranslation:
    translation = MenuTranslation.objects.get(menu_id=menu_id, language_code=language_code)
    translation.name = name
    translation.save(update_fields=["name", "updated_at"])
    return translation


def delete_menu_translation(*, menu_id: int, language_code: str) -> None:
    MenuTranslation.objects.filter(menu_id=menu_id, language_code=language_code).delete()


def get_menu_translations(*, menu_id: int) -> list[MenuTranslation]:
    return list(MenuTranslation.objects.filter(menu_id=menu_id))


def create_category_translation(*, category_id: int, language_code: str, name: str) -> MenuCategoryTranslation:
    return MenuCategoryTranslation.objects.create(
        category_id=category_id,
        language_code=language_code,
        name=name,
    )


def update_category_translation(*, category_id: int, language_code: str, name: str) -> MenuCategoryTranslation:
    translation = MenuCategoryTranslation.objects.get(category_id=category_id, language_code=language_code)
    translation.name = name
    translation.save(update_fields=["name", "updated_at"])
    return translation


def delete_category_translation(*, category_id: int, language_code: str) -> None:
    MenuCategoryTranslation.objects.filter(category_id=category_id, language_code=language_code).delete()


def get_category_translations(*, category_id: int) -> list[MenuCategoryTranslation]:
    return list(MenuCategoryTranslation.objects.filter(category_id=category_id))


def create_item_translation(
    *, menu_item_id: int, language_code: str, name: str,
    description: str | None = None,
) -> MenuItemTranslation:
    return MenuItemTranslation.objects.create(
        menu_item_id=menu_item_id,
        language_code=language_code,
        name=name,
        description=description or "",
    )


def update_item_translation(
    *, menu_item_id: int, language_code: str, name: str,
    description: str | None = None,
) -> MenuItemTranslation:
    translation = MenuItemTranslation.objects.get(menu_item_id=menu_item_id, language_code=language_code)
    translation.name = name
    if description is not None:
        translation.description = description
    translation.save(update_fields=["name", "description", "updated_at"])
    return translation


def delete_item_translation(*, menu_item_id: int, language_code: str) -> None:
    MenuItemTranslation.objects.filter(menu_item_id=menu_item_id, language_code=language_code).delete()


def get_item_translations(*, menu_item_id: int) -> list[MenuItemTranslation]:
    return list(MenuItemTranslation.objects.filter(menu_item_id=menu_item_id))


def _unique_copy_name(menu: Menu, base: str) -> str:
    """A '(copy)' name that satisfies the unique (menu, name) constraint."""
    name = f"{base} (copy)"
    counter = 2
    while MenuItem.objects.filter(menu=menu, name=name).exists():
        name = f"{base} (copy {counter})"
        counter += 1
    return name


def get_upsells_for_item(
    *,
    restaurant_id: int,
    item: MenuItem,
    guest_token: str | None = None,
    limit: int = 6,
) -> list[MenuItem]:
    """Suggest complementary items for a dish.

    Uses co-occurrence from completed order history, then fills remaining slots
    with the fallback set so an available dish never yields an empty result.
    """
    suggestions = list(
        get_upsell_suggestions(
            restaurant_id=restaurant_id,
            target_item=item,
            guest_token=guest_token,
            limit=limit,
        )
    )
    if len(suggestions) >= limit:
        return suggestions

    picked_ids = {s.pk for s in suggestions}
    fallback = get_default_upsell_items(
        restaurant_id=restaurant_id,
        target_item=item,
        guest_token=guest_token,
        limit=limit - len(suggestions),
        exclude_ids=picked_ids,
    )
    return suggestions + list(fallback)


def create_allergen_translation(*, allergen_key: str, language_code: str, name: str) -> AllergenTranslation:
    allergen = Allergen.objects.get(key=allergen_key)
    return AllergenTranslation.objects.create(
        allergen=allergen,
        language_code=language_code,
        name=name,
    )


def update_allergen_translation(*, allergen_key: str, language_code: str, name: str) -> AllergenTranslation:
    translation = AllergenTranslation.objects.get(allergen__key=allergen_key, language_code=language_code)
    translation.name = name
    translation.save(update_fields=["name", "updated_at"])
    return translation


def delete_allergen_translation(*, allergen_key: str, language_code: str) -> None:
    AllergenTranslation.objects.filter(allergen__key=allergen_key, language_code=language_code).delete()


def get_allergen_translations(*, allergen_key: str) -> list[AllergenTranslation]:
    return list(AllergenTranslation.objects.filter(allergen__key=allergen_key))


def _check_duplicate_ingredient_name(*, ingredient_id: int, language_code: str, name: str) -> None:
    """Raise ValidationError if another ingredient in the same restaurant
    already has an English translation with this name."""
    if language_code != "en":
        return
    ingredient = Ingredient.objects.only("restaurant_id").get(pk=ingredient_id)
    if IngredientTranslation.objects.filter(
        language_code="en",
        name=name,
        ingredient__restaurant_id=ingredient.restaurant_id,
    ).exclude(ingredient_id=ingredient_id).exists():
        raise ValidationError(
            f'Another ingredient in this restaurant already has the English name "{name}".'
        )


def create_ingredient_translation(
    *, ingredient_id: int, language_code: str, name: str,
) -> IngredientTranslation:
    _check_duplicate_ingredient_name(ingredient_id=ingredient_id, language_code=language_code, name=name)
    return IngredientTranslation.objects.create(
        ingredient_id=ingredient_id,
        language_code=language_code,
        name=name,
    )


def update_ingredient_translation(
    *, ingredient_id: int, language_code: str, name: str,
) -> IngredientTranslation:
    _check_duplicate_ingredient_name(ingredient_id=ingredient_id, language_code=language_code, name=name)
    translation = IngredientTranslation.objects.get(ingredient_id=ingredient_id, language_code=language_code)
    translation.name = name
    translation.save(update_fields=["name", "updated_at"])
    return translation


def delete_ingredient_translation(*, ingredient_id: int, language_code: str) -> None:
    IngredientTranslation.objects.filter(ingredient_id=ingredient_id, language_code=language_code).delete()


def get_ingredient_translations(*, ingredient_id: int) -> list[IngredientTranslation]:
    return list(IngredientTranslation.objects.filter(ingredient_id=ingredient_id))
