from rest_framework import serializers

from .models import Menu, MenuCategory, MenuItem


class MenuCategorySerializer(serializers.ModelSerializer[MenuCategory]):
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
    menu: serializers.PrimaryKeyRelatedField[Menu] = serializers.PrimaryKeyRelatedField(
        read_only=True
    )
    category: serializers.PrimaryKeyRelatedField[MenuCategory] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
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
    items: serializers.PrimaryKeyRelatedField[MenuItem] = (
        serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    )
    categories: serializers.PrimaryKeyRelatedField[MenuCategory] = (
        serializers.PrimaryKeyRelatedField(many=True, read_only=True)
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
