from __future__ import annotations

import os
from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import QuerySet
from rest_framework import serializers

from .models import Menu, MenuCategory, MenuItem


def reorder(queryset: QuerySet[Any], entries: list[dict[str, Any]]) -> None:
    """Apply a list of {public_id, sort_order} to a (restaurant-scoped) queryset
    in one atomic bulk update. Unknown/foreign ids are ignored. Works for both
    categories and items."""
    objs_by_id = {
        obj.public_id: obj
        for obj in queryset.filter(public_id__in=[e["public_id"] for e in entries])
    }
    to_update: list[Any] = []
    for entry in entries:
        obj = objs_by_id.get(entry["public_id"])
        if obj is not None and obj.sort_order != entry["sort_order"]:
            obj.sort_order = entry["sort_order"]
            to_update.append(obj)

    if to_update:
        with transaction.atomic():
            type(to_update[0]).objects.bulk_update(to_update, ["sort_order"])


def bulk_update_items(*, restaurant_id: int, data: dict[str, Any]) -> dict[str, int]:
    """Hide/show, set the category of, or delete several dishes at once. Only the
    restaurant's own items are touched; unknown ids are ignored."""
    items = MenuItem.objects.filter(restaurant_id=restaurant_id, public_id__in=data["ids"])

    if data["action"] == "delete":
        count, _ = items.delete()
        return {"deleted": count}

    if data["action"] == "set_available":
        return {"updated": items.update(is_available=data["is_available"])}

    # set_category: resolve a restaurant-owned category (or null to clear).
    category = None
    if data.get("category") is not None:
        category = MenuCategory.objects.filter(
            public_id=data["category"], menu__restaurant_id=restaurant_id
        ).first()
        if category is None:
            raise serializers.ValidationError({"category": "Category not found."})
        # A category can only hold dishes from its own menu.
        if items.exclude(menu_id=category.menu_id).exists():
            raise serializers.ValidationError({"category": "Category must belong to the items' menu."})
    return {"updated": items.update(category=category)}


def duplicate_item(item: MenuItem) -> MenuItem:
    """Server-side copy of a dish, including its image file."""
    copy = MenuItem(
        restaurant=item.restaurant,
        menu=item.menu,
        category=item.category,
        name=_unique_copy_name(item.menu, item.name),
        description=item.description,
        ingredients=list(item.ingredients or []),
        allergens=list(item.allergens or []),
        weight_grams=item.weight_grams,
        price=item.price,
        is_available=item.is_available,
        sort_order=item.sort_order,
    )
    if item.image:
        item.image.open("rb")
        try:
            copy.image.save(
                os.path.basename(item.image.name),
                ContentFile(item.image.read()),
                save=False,
            )
        finally:
            item.image.close()
    copy.save()
    return copy


def _unique_copy_name(menu: Menu, base: str) -> str:
    """A '(copy)' name that satisfies the unique (menu, name) constraint."""
    name = f"{base} (copy)"
    counter = 2
    while MenuItem.objects.filter(menu=menu, name=name).exists():
        name = f"{base} (copy {counter})"
        counter += 1
    return name
