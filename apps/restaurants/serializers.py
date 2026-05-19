from rest_framework import serializers

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


class RestaurantSettingsSerializer(serializers.ModelSerializer[RestaurantSettings]):
    restaurant: serializers.PrimaryKeyRelatedField[Restaurant] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
    )

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
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class TableSerializer(serializers.ModelSerializer[Table]):
    restaurant: serializers.PrimaryKeyRelatedField[Restaurant] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
    )

    class Meta:
        model = Table
        fields = [
            "public_id",
            "restaurant",
            "table_number",
            "capacity",
            "status",
            "position_x",
            "position_y",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]
