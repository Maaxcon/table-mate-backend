from typing import Any, cast

from django.db import transaction
from django.db.models import Model, QuerySet
from rest_framework import serializers

from apps.restaurants.models import Restaurant
from common.api import PublicIdRelatedField, get_restaurant_id_from_auth

from .models import (
    Allergen,
    Ingredient,
    Menu,
    MenuCategory,
    MenuItem,
    MenuItemAllergen,
    MenuItemIngredient,
)
from .services import prune_orphans
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
    ingredients = serializers.SerializerMethodField()
    allergens = serializers.SerializerMethodField()
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

    def get_ingredients(self, obj: MenuItem) -> list[str]:
        return self._localized_m2m_names(obj.item_ingredients.all(), "ingredient")

    def get_allergens(self, obj: MenuItem) -> list[str]:
        return self._localized_m2m_names(obj.item_allergens.all(), "allergen")

    def _localized_m2m_names(self, through_qs: QuerySet[Any], fk_name: str) -> list[str]:
        request = self.context.get("request")
        lang = getattr(request, "active_language", None) if request else None
        names: list[str] = []
        for through in through_qs:
            entity = getattr(through, fk_name)
            by_code = {t.language_code: t.name for t in entity.translations.all()}
            name = by_code.get(lang, entity.name)
            names.append(name)
        return names

    def to_representation(self, instance: MenuItem) -> dict[str, Any]:
        data = super().to_representation(instance)
        request = self.context.get("request")
        lang = getattr(request, "active_language", None) if request else None
        if lang:
            localized = get_localized_content(instance, lang)
            for field in ("name", "description"):
                if field in localized and localized[field] is not None:
                    data[field] = localized[field]
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

    class Meta:
        fields = ["language_code", "name", "description"]


class AdminMenuSerializer(serializers.ModelSerializer[Menu]):
    """Writable menu serializer for the admin panel."""

    translations = serializers.SerializerMethodField()

    class Meta:
        model = Menu
        fields = ["public_id", "name", "is_active", "translations", "created_at", "updated_at"]
        read_only_fields = ["public_id", "created_at", "updated_at"]

    def get_translations(self, obj: Menu) -> list[dict[str, str]]:
        return MenuTranslationSerializer(obj.translations.all(), many=True).data  # type: ignore[return-value]


class AdminMenuCategorySerializer(serializers.ModelSerializer[MenuCategory]):
    """Writable category serializer. The menu is referenced by its public id and
    must belong to the admin's restaurant (validated in the view's queryset)."""

    menu: PublicIdRelatedField[Menu] = PublicIdRelatedField(
        queryset=Menu.objects.all(),
    )
    translations = serializers.SerializerMethodField()

    class Meta:
        model = MenuCategory
        fields = ["public_id", "menu", "name", "sort_order", "color", "translations", "created_at", "updated_at"]
        read_only_fields = ["public_id", "created_at", "updated_at"]

    def get_translations(self, obj: MenuCategory) -> list[dict[str, str]]:
        return MenuCategoryTranslationSerializer(obj.translations.all(), many=True).data  # type: ignore[return-value]


class LocalizedM2MNamesField(serializers.ListField):
    """ListField that reads localized vocabulary display names from a through model
    on read, and writes name strings on write (standard ListField behavior)."""

    fk_name: str

    def __init__(self, fk_name: str, **kwargs: Any) -> None:
        self.fk_name = fk_name
        super().__init__(**kwargs)

    def get_attribute(self, instance: Model) -> list[str]:
        request = self.context.get("request")
        lang = getattr(request, "active_language", None) if request else None
        names: list[str] = []
        menu_item = cast(MenuItem, instance)
        through_qs = (
            menu_item.item_ingredients.all()
            if self.fk_name == "ingredient"
            else menu_item.item_allergens.all()
        )
        for through in through_qs:
            entity = getattr(through, self.fk_name)
            by_code = {t.language_code: t.name for t in entity.translations.all()}
            name = by_code.get(lang, entity.name)
            names.append(name)
        return names


class AdminMenuItemSerializer(serializers.ModelSerializer[MenuItem]):
    """Writable menu item serializer for the admin panel. Menu and category are
    referenced by public id and limited to the admin's restaurant in the view."""

    menu: PublicIdRelatedField[Menu] = PublicIdRelatedField(queryset=Menu.objects.all())
    category: PublicIdRelatedField[MenuCategory] = PublicIdRelatedField(
        queryset=MenuCategory.objects.all(),
        required=False,
        allow_null=True,
    )
    ingredients = LocalizedM2MNamesField(
        fk_name="ingredient",
        child=serializers.CharField(),
        required=False,
    )
    allergens = LocalizedM2MNamesField(
        fk_name="allergen",
        child=serializers.CharField(),
        required=False,
    )
    # Annotated in AdminMenuItemViewSet.get_queryset; read-only for the dashboard.
    likes_count = serializers.SerializerMethodField()
    translations = serializers.SerializerMethodField()

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
            "translations",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "likes_count", "created_at", "updated_at"]

    def get_likes_count(self, obj: MenuItem) -> int:
        value = getattr(obj, "likes_count", None)
        return value if value is not None else 0

    def get_translations(self, obj: MenuItem) -> list[dict[str, str | None]]:
        return MenuItemTranslationSerializer(obj.translations.all(), many=True).data  # type: ignore[return-value]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        menu = attrs.get("menu") or getattr(self.instance, "menu", None)
        category = attrs["category"] if "category" in attrs else getattr(self.instance, "category", None)
        if category is not None and menu is not None and category.menu_id != menu.id:
            raise serializers.ValidationError({"category": "Category must belong to the selected menu."})
        return attrs

    def create(self, validated_data: dict[str, Any], **kwargs: Any) -> MenuItem:
        ingredient_keys = validated_data.pop("ingredients", [])
        allergen_keys = validated_data.pop("allergens", [])
        instance = MenuItem.objects.create(**validated_data, **kwargs)
        self._set_allergens(instance, allergen_keys)
        self._set_ingredients(instance, ingredient_keys)
        return instance

    def update(self, instance: MenuItem, validated_data: dict[str, Any]) -> MenuItem:
        ingredient_names = validated_data.pop("ingredients", None)
        allergen_names = validated_data.pop("allergens", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        with transaction.atomic():
            instance.save()
            if allergen_names is not None:
                removed_allergen_ids = list(instance.item_allergens.values_list("allergen_id", flat=True))
                instance.item_allergens.all().delete()
                self._set_allergens(instance, allergen_names)
                prune_orphans(
                    entity_model=Allergen,
                    through_model=MenuItemAllergen,
                    removed_ids=removed_allergen_ids,
                )
            if ingredient_names is not None:
                removed_ingredient_ids = list(instance.item_ingredients.values_list("ingredient_id", flat=True))
                instance.item_ingredients.all().delete()
                self._set_ingredients(instance, ingredient_names)
                prune_orphans(
                    entity_model=Ingredient,
                    through_model=MenuItemIngredient,
                    removed_ids=removed_ingredient_ids,
                )
        return instance

    def _set_allergens(self, instance: MenuItem, names: list[str]) -> None:
        for sort_order, name in enumerate(names):
            allergen = self._get_or_create_allergen(instance.restaurant_id, name)
            MenuItemAllergen.objects.create(
                menu_item=instance,
                allergen=allergen,
                sort_order=sort_order,
            )

    def _set_ingredients(self, instance: MenuItem, names: list[str]) -> None:
        for sort_order, name in enumerate(names):
            ingredient = self._get_or_create_ingredient(instance.restaurant_id, name)
            MenuItemIngredient.objects.create(
                menu_item=instance,
                ingredient=ingredient,
                sort_order=sort_order,
            )

    def _get_or_create_allergen(self, restaurant_id: int, name: str) -> Allergen:
        normalized = name.strip()
        existing = Allergen.objects.filter(
            restaurant_id=restaurant_id,
            name__iexact=normalized,
        ).first()
        if existing is not None:
            return existing
        return Allergen.objects.create(
            restaurant_id=restaurant_id,
            name=normalized,
        )

    def _get_or_create_ingredient(self, restaurant_id: int, name: str) -> Ingredient:
        normalized = name.strip()
        existing = Ingredient.objects.filter(
            restaurant_id=restaurant_id,
            name__iexact=normalized,
        ).first()
        if existing is not None:
            return existing
        return Ingredient.objects.create(
            restaurant_id=restaurant_id,
            name=normalized,
        )


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


class AllergenTranslationSerializer(serializers.Serializer[Any]):
    language_code = serializers.CharField(max_length=10)
    name = serializers.CharField(max_length=255)

    class Meta:
        fields = ["language_code", "name"]


class AdminAllergenSerializer(serializers.ModelSerializer[Allergen]):
    translations = serializers.SerializerMethodField()

    class Meta:
        model = Allergen
        fields = ["public_id", "name", "sort_order", "translations", "created_at", "updated_at"]
        read_only_fields = ["public_id", "created_at", "updated_at"]

    def get_translations(self, obj: Allergen) -> list[dict[str, str]]:
        return AllergenTranslationSerializer(obj.translations.all(), many=True).data  # type: ignore[return-value]

    def validate_name(self, value: str) -> str:
        allergen_id = self.instance.pk if self.instance else None
        request = self.context.get("request")
        if request is None:
            return value
        restaurant_id = get_restaurant_id_from_auth(request)
        if restaurant_id is None:
            return value
        qs = Allergen.objects.filter(
            restaurant_id=restaurant_id,
            name__iexact=value.strip(),
        )
        if allergen_id:
            qs = qs.exclude(pk=allergen_id)
        if qs.exists():
            raise serializers.ValidationError(
                f'An allergen with name "{value}" already exists in this restaurant.'
            )
        return value


class IngredientTranslationSerializer(serializers.Serializer[Any]):
    language_code = serializers.CharField(max_length=10)
    name = serializers.CharField(max_length=255)

    class Meta:
        fields = ["language_code", "name"]


class AdminIngredientSerializer(serializers.ModelSerializer[Ingredient]):
    translations = serializers.SerializerMethodField()

    class Meta:
        model = Ingredient
        fields = ["public_id", "name", "sort_order", "translations", "created_at", "updated_at"]
        read_only_fields = ["public_id", "created_at", "updated_at"]

    def get_translations(self, obj: Ingredient) -> list[dict[str, str]]:
        return IngredientTranslationSerializer(obj.translations.all(), many=True).data  # type: ignore[return-value]

    def validate_name(self, value: str) -> str:
        ingredient_id = self.instance.pk if self.instance else None
        request = self.context.get("request")
        if request is None:
            return value
        restaurant_id = get_restaurant_id_from_auth(request)
        if restaurant_id is None:
            return value
        qs = Ingredient.objects.filter(
            restaurant_id=restaurant_id,
            name__iexact=value.strip(),
        )
        if ingredient_id:
            qs = qs.exclude(pk=ingredient_id)
        if qs.exists():
            raise serializers.ValidationError(
                f'An ingredient with name "{value}" already exists in this restaurant.'
            )
        return value
