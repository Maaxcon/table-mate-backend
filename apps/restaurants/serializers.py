from rest_framework import serializers

from apps.authentication.models import RoleCode, User
from common.api import PublicIdRelatedField

from .models import Restaurant, RestaurantSettings, Table, Zone


class RestaurantSerializer(serializers.ModelSerializer[Restaurant]):
    class Meta:
        model = Restaurant
        fields = [
            "public_id",
            "name",
            "address",
            "phone",
            "telegram_url",
            "facebook_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class EmployeeSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = [
            "public_id",
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "is_active",
        ]
        read_only_fields = ["public_id", "email"]

    def validate_role(self, value: str) -> str:
        if value == RoleCode.CUSTOMER:
            raise serializers.ValidationError("An employee cannot be set to the customer role.")
        return value


class EmployeeCreateSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = [
            "public_id",
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "is_active",
        ]
        read_only_fields = ["public_id", "is_active"]

    def validate_role(self, value: str) -> str:
        if value == RoleCode.CUSTOMER:
            raise serializers.ValidationError("An employee cannot be set to the customer role.")
        return value

    def validate_email(self, value: str) -> str:
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value


class PublicRestaurantSettingsSerializer(serializers.ModelSerializer[RestaurantSettings]):
    class Meta:
        model = RestaurantSettings
        fields = ["currency", "timezone", "working_hours", "rating", "eta_min_minutes", "eta_max_minutes", "price_band"]
        read_only_fields = fields


class BookingSettingsSerializer(serializers.ModelSerializer[RestaurantSettings]):
    class Meta:
        model = RestaurantSettings
        fields = ["currency", "timezone", "working_hours"]
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


class ZoneSerializer(serializers.ModelSerializer[Zone]):
    class Meta:
        model = Zone
        fields = [
            "public_id",
            "name",
            "sort_order",
        ]
        read_only_fields = fields


class TableSerializer(serializers.ModelSerializer[Table]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    zone = ZoneSerializer(read_only=True, allow_null=True)

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
            "zone",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]
