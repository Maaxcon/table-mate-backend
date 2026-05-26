from rest_framework import serializers

from apps.restaurants.models import Restaurant
from common.api import PublicIdRelatedField

from .models import Menu, MenuCategory, MenuItem


class MenuCategorySerializer(serializers.ModelSerializer[MenuCategory]):
    menu: PublicIdRelatedField[Menu] = PublicIdRelatedField(read_only=True)

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
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    menu: PublicIdRelatedField[Menu] = PublicIdRelatedField(read_only=True)
    category: PublicIdRelatedField[MenuCategory] = PublicIdRelatedField(read_only=True)

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
