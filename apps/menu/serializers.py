from typing import Any

from rest_framework import serializers

from apps.restaurants.models import Restaurant
from common.api import PublicIdRelatedField

from .allergens import get_allergen_labels
from .models import Menu, MenuCategory, MenuItem
from .services.localization import get_localized_content


class MenuCategorySerializer(serializers.ModelSerializer[MenuCategory]):
    menu: PublicIdRelatedField[Menu] = PublicIdRelatedField(read_only=True)
    _lang = serializers.SerializerMethodField(read_only=True)
    _is_fallback = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = MenuCategory
        fields = [
            "public_id",
            "menu",
            "name",
            "sort_order",
            "color",
            "_lang",
            "_is_fallback",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]

    def get__lang(self, obj: MenuCategory) -> str | None:
        request = self.context.get("request")
        return getattr(request, "active_language", None) if request else None

    def get__is_fallback(self, obj: MenuCategory) -> bool:
        request = self.context.get("request")
        return getattr(request, "active_language_is_fallback", False) if request else False

    def to_representation(self, instance: MenuCategory) -> dict[str, Any]:
        data = super().to_representation(instance)
        request = self.context.get("request")
        lang = getattr(request, "active_language", None) if request else None
        if lang:
            _localized = getattr(instance, "_localized", None)
            if _localized and isinstance(_localized, dict) and "name" in _localized:
                data["name"] = _localized["name"]
        return data


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
    _lang = serializers.SerializerMethodField(read_only=True)
    _is_fallback = serializers.SerializerMethodField(read_only=True)

    def get_likes_count(self, obj: MenuItem) -> int:
        val = getattr(obj, "likes_count", None)
        return int(val) if val is not None else 0

    def get_is_liked(self, obj: MenuItem) -> bool:
        val = getattr(obj, "is_liked", None)
        return bool(val) if val is not None else False

    def get__lang(self, obj: MenuItem) -> str | None:
        request = self.context.get("request")
        return getattr(request, "active_language", None) if request else None

    def get__is_fallback(self, obj: MenuItem) -> bool:
        request = self.context.get("request")
        return getattr(request, "active_language_is_fallback", False) if request else False

    def to_representation(self, instance: MenuItem) -> dict[str, Any]:
        data = super().to_representation(instance)
        request = self.context.get("request")
        lang = getattr(request, "active_language", None) if request else None
        if lang:
            localized = get_localized_content(instance, lang)
            for field in ("name", "description"):
                if field in localized and localized[field] is not None:
                    data[field] = localized[field]
            if "allergens" in data and isinstance(data["allergens"], list):
                en_labels = get_allergen_labels("en")
                localized_labels = get_allergen_labels(lang)
                allergen_labels_map = dict(zip(en_labels, localized_labels, strict=False))
                data["allergens"] = [allergen_labels_map.get(a, a) for a in data["allergens"]]
        return data

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
            "_lang",
            "_is_fallback",
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
    _lang = serializers.SerializerMethodField(read_only=True)
    _is_fallback = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Menu
        fields = [
            "public_id",
            "restaurant",
            "name",
            "is_active",
            "items",
            "categories",
            "_lang",
            "_is_fallback",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]

    def get__lang(self, obj: Menu) -> str | None:
        request = self.context.get("request")
        return getattr(request, "active_language", None) if request else None

    def get__is_fallback(self, obj: Menu) -> bool:
        request = self.context.get("request")
        return getattr(request, "active_language_is_fallback", False) if request else False

    def to_representation(self, instance: Menu) -> dict[str, Any]:
        data = super().to_representation(instance)
        request = self.context.get("request")
        lang = getattr(request, "active_language", None) if request else None
        if lang:
            _localized = getattr(instance, "_localized", None)
            if _localized and isinstance(_localized, dict) and "name" in _localized:
                data["name"] = _localized["name"]
        return data


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


class UpsellSuggestionResponseSerializer(serializers.Serializer[Any]):
    """Read-only envelope for smart upsell suggestions.

    ``results`` reuses the canonical ``MenuItemSerializer`` so clients render
    suggestions with the same item component used across the menu.
    """

    count = serializers.IntegerField(min_value=0)
    results = MenuItemSerializer(many=True)


class ReorderEntrySerializer(serializers.Serializer[Any]):
    """One {public_id, sort_order} pair for a bulk reorder request."""

    public_id = serializers.UUIDField()
    sort_order = serializers.IntegerField(min_value=0)


class MenuTranslationSerializer(serializers.Serializer[Any]):
    language_code = serializers.CharField(max_length=10)
    name = serializers.CharField(max_length=255)

    class Meta:
        fields = ["language_code", "name"]


class MenuCategoryTranslationSerializer(serializers.Serializer[Any]):
    language_code = serializers.CharField(max_length=10)
    name = serializers.CharField(max_length=255)

    class Meta:
        fields = ["language_code", "name"]


class MenuItemTranslationSerializer(serializers.Serializer[Any]):
    language_code = serializers.CharField(max_length=10)
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    ingredients = serializers.ListField(child=serializers.CharField(), required=False)

    class Meta:
        fields = ["language_code", "name", "description", "ingredients"]


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
