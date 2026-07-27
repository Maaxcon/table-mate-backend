from typing import Any

from rest_framework import serializers

from apps.restaurants.models import Restaurant
from common.api import PublicIdRelatedField

from .models import Allergen, Menu, MenuCategory, MenuItem


class AllergenSerializer(serializers.ModelSerializer[Allergen]):
    class Meta:
        model = Allergen
        fields = ["public_id", "name", "created_at", "updated_at"]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class MenuCategorySerializer(serializers.ModelSerializer[MenuCategory]):
    menu: PublicIdRelatedField[Menu] = PublicIdRelatedField(read_only=True)

    class Meta:
        model = MenuCategory
        fields = [
            "public_id",
            "menu",
            "name",
            "sort_order",
            "color",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class MenuItemSerializer(serializers.ModelSerializer[MenuItem]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    menu: PublicIdRelatedField[Menu] = PublicIdRelatedField(read_only=True)
    category: PublicIdRelatedField[MenuCategory] = PublicIdRelatedField(
        read_only=True,
        allow_null=True,
    )
    ingredients = serializers.ListField(child=serializers.CharField(), read_only=True)
    allergens = serializers.ListField(child=serializers.CharField(), read_only=True)
    likes_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()

    def get_likes_count(self, obj: MenuItem) -> int:
        val = getattr(obj, "likes_count", None)
        return int(val) if val is not None else 0

    def get_is_liked(self, obj: MenuItem) -> bool:
        val = getattr(obj, "is_liked", None)
        return bool(val) if val is not None else False

    class Meta:
        model = MenuItem
        fields = [
            "public_id",
            "restaurant",
            "menu",
            "category",
            "name",
            "description",
            "ingredients",
            "allergens",
            "weight_grams",
            "image",
            "likes_count",
            "is_liked",
            "price",
            "is_available",
            "sort_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class MenuSerializer(serializers.ModelSerializer[Menu]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    items: PublicIdRelatedField[MenuItem] = PublicIdRelatedField(
        many=True,
        read_only=True,
    )
    categories: PublicIdRelatedField[MenuCategory] = PublicIdRelatedField(
        many=True,
        read_only=True,
    )

    class Meta:
        model = Menu
        fields = [
            "public_id",
            "restaurant",
            "name",
            "is_active",
            "items",
            "categories",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class AdminMenuSerializer(serializers.ModelSerializer[Menu]):
    """Writable menu serializer for the admin panel."""

    class Meta:
        model = Menu
        fields = ["public_id", "name", "is_active", "created_at", "updated_at"]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class AdminMenuCategorySerializer(serializers.ModelSerializer[MenuCategory]):
    """Writable category serializer. The menu is referenced by its public id and
    must belong to the admin's restaurant (validated in the view's queryset)."""

    menu: PublicIdRelatedField[Menu] = PublicIdRelatedField(
        queryset=Menu.objects.all(),
    )

    class Meta:
        model = MenuCategory
        fields = ["public_id", "menu", "name", "sort_order", "color", "created_at", "updated_at"]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class AdminMenuItemSerializer(serializers.ModelSerializer[MenuItem]):
    """Writable menu item serializer for the admin panel. Menu and category are
    referenced by public id and limited to the admin's restaurant in the view."""

    menu: PublicIdRelatedField[Menu] = PublicIdRelatedField(queryset=Menu.objects.all())
    category: PublicIdRelatedField[MenuCategory] = PublicIdRelatedField(
        queryset=MenuCategory.objects.all(),
        required=False,
        allow_null=True,
    )
    ingredients = serializers.ListField(child=serializers.CharField(), required=False)
    allergens = serializers.ListField(child=serializers.CharField(), required=False)
    # Annotated in AdminMenuItemViewSet.get_queryset; read-only for the dashboard.
    likes_count = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = [
            "public_id",
            "menu",
            "category",
            "name",
            "description",
            "ingredients",
            "allergens",
            "weight_grams",
            "image",
            "price",
            "is_available",
            "sort_order",
            "likes_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "likes_count", "created_at", "updated_at"]

    def get_likes_count(self, obj: MenuItem) -> int:
        value = getattr(obj, "likes_count", None)
        return value if value is not None else 0

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        menu = attrs.get("menu") or getattr(self.instance, "menu", None)
        # Fall back to the existing category when the PATCH doesn't touch it, so
        # changing only the menu still re-checks the current category.
        category = attrs["category"] if "category" in attrs else getattr(self.instance, "category", None)
        if category is not None and menu is not None and category.menu_id != menu.id:
            raise serializers.ValidationError({"category": "Category must belong to the selected menu."})
        return attrs


class ToggleMenuItemLikeRequestSerializer(serializers.Serializer[Any]):
    guest_token = serializers.CharField(max_length=64)


class ToggleMenuItemLikeResponseSerializer(serializers.Serializer[Any]):
    public_id = serializers.UUIDField()
    is_liked = serializers.BooleanField()
    likes_count = serializers.IntegerField(min_value=0)


class ReorderEntrySerializer(serializers.Serializer[Any]):
    """One {public_id, sort_order} pair for a bulk reorder request."""

    public_id = serializers.UUIDField()
    sort_order = serializers.IntegerField(min_value=0)


class BulkItemActionSerializer(serializers.Serializer[Any]):
    """A bulk operation over several menu items, selected by public id.

    - ``set_available`` needs ``is_available``
    - ``set_category`` needs ``category`` (may be null to clear it)
    - ``delete`` needs nothing else
    """

    ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    action = serializers.ChoiceField(choices=["set_available", "set_category", "delete"])
    is_available = serializers.BooleanField(required=False)
    category = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["action"] == "set_available" and "is_available" not in attrs:
            raise serializers.ValidationError({"is_available": "Required for this action."})
        if attrs["action"] == "set_category" and "category" not in attrs:
            raise serializers.ValidationError({"category": "Required for this action."})
        return attrs
