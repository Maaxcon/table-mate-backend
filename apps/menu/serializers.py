from rest_framework import serializers

from apps.restaurants.models import Restaurant

from .models import Menu, MenuCategory, MenuItem


class MenuCategorySerializer(serializers.ModelSerializer[MenuCategory]):
    menu: serializers.SlugRelatedField[Menu] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )

    class Meta:
        model = MenuCategory
        fields = [
            "public_id",
            "menu",
            "name",
            "sort_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class MenuItemSerializer(serializers.ModelSerializer[MenuItem]):
    restaurant: serializers.SlugRelatedField[Restaurant] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )
    menu: serializers.SlugRelatedField[Menu] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )
    category: serializers.SlugRelatedField[MenuCategory] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )

    class Meta:
        model = MenuItem
        fields = [
            "public_id",
            "restaurant",
            "menu",
            "category",
            "name",
            "description",
            "price",
            "is_available",
            "sort_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class MenuSerializer(serializers.ModelSerializer[Menu]):
    restaurant: serializers.SlugRelatedField[Restaurant] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )
    items: serializers.SlugRelatedField[MenuItem] = serializers.SlugRelatedField(
        slug_field="public_id",
        many=True,
        read_only=True,
    )
    categories: serializers.SlugRelatedField[MenuCategory] = (
        serializers.SlugRelatedField(
            slug_field="public_id",
            many=True,
            read_only=True,
        )
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
