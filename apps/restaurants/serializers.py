from rest_framework import serializers

from common.api import PublicIdRelatedField

from .models import Restaurant, RestaurantSettings, Table


class RestaurantSerializer(serializers.ModelSerializer[Restaurant]):
    class Meta:
        model = Restaurant
        fields = [
            "public_id",
            "name",
            "address",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class PublicRestaurantSettingsSerializer(serializers.ModelSerializer[RestaurantSettings]):
    class Meta:
        model = RestaurantSettings
        fields = ["currency", "timezone", "working_hours", "rating", "eta_min_minutes", "eta_max_minutes", "price_band"]
        read_only_fields = fields


class PublicRestaurantSerializer(serializers.ModelSerializer[Restaurant]):
    settings = PublicRestaurantSettingsSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Restaurant
        fields = ["public_id", "name", "address", "phone", "cover_image", "telegram_url", "facebook_url", "settings"]
        read_only_fields = [
            "public_id",
            "name",
            "address",
            "phone",
            "cover_image",
            "telegram_url",
            "facebook_url",
            "settings",
        ]


class RestaurantSettingsSerializer(serializers.ModelSerializer[RestaurantSettings]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)

    class Meta:
        model = RestaurantSettings
        fields = [
            "public_id",
            "restaurant",
            "timezone",
            "currency",
            "locale",
            "default_tax_rate",
            "default_service_charge",
            "working_hours",
            "rating",
            "eta_min_minutes",
            "eta_max_minutes",
            "price_band",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class TableSerializer(serializers.ModelSerializer[Table]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)

    class Meta:
        model = Table
        fields = [
            "public_id",
            "restaurant",
            "table_number",
            "capacity",
            "status",
            "shape",
            "active",
            "position_x",
            "position_y",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]
