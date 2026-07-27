from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.authentication.models import RoleCode, User
from common.api import PublicIdRelatedField

from .models import Restaurant, RestaurantSettings, Table, Zone, validate_working_hours


class WorkingHoursDaySerializer(serializers.Serializer[Any]):
    open = serializers.CharField()
    close = serializers.CharField()


class WorkingHoursSerializer(serializers.Serializer[Any]):
    """Schema shape for the working_hours JSON: optional mon–sun, each open/close.
    Used only to type the OpenAPI schema; validation stays in validate_working_hours."""

    mon = WorkingHoursDaySerializer(required=False)
    tue = WorkingHoursDaySerializer(required=False)
    wed = WorkingHoursDaySerializer(required=False)
    thu = WorkingHoursDaySerializer(required=False)
    fri = WorkingHoursDaySerializer(required=False)
    sat = WorkingHoursDaySerializer(required=False)
    sun = WorkingHoursDaySerializer(required=False)


@extend_schema_field(WorkingHoursSerializer)
class _WorkingHoursField(serializers.JSONField):
    """JSONField that advertises the WorkingHours shape in the OpenAPI schema."""


def working_hours_field(**kwargs: Any) -> serializers.JSONField:
    return _WorkingHoursField(validators=[validate_working_hours], **kwargs)


class AdminOverviewSerializer(serializers.Serializer[Any]):
    """Counts for the admin dashboard, scoped to the admin's restaurant."""

    menus_total = serializers.IntegerField()
    menus_active = serializers.IntegerField()
    dishes_total = serializers.IntegerField()
    dishes_hidden = serializers.IntegerField()
    categories_total = serializers.IntegerField()
    staff_total = serializers.IntegerField()
    staff_active = serializers.IntegerField()


class RestaurantSerializer(serializers.ModelSerializer[Restaurant]):
    # Working hours live on RestaurantSettings; expose them here so the admin can
    # edit them with the restaurant profile. The view writes them to settings.
    working_hours = working_hours_field(required=False, write_only=True)

    class Meta:
        model = Restaurant
        fields = [
            "public_id",
            "name",
            "address",
            "phone",
            "telegram_url",
            "facebook_url",
            "working_hours",
            "cover_image",
            "created_at",
            "updated_at",
        ]
        # cover_image is uploaded via the dedicated `cover` action, so it is
        # read-only here (the profile PATCH ignores it).
        read_only_fields = ["public_id", "cover_image", "created_at", "updated_at"]

    def to_representation(self, instance: Restaurant) -> dict[str, object]:
        data = super().to_representation(instance)
        try:
            data["working_hours"] = instance.settings.working_hours
        except RestaurantSettings.DoesNotExist:
            data["working_hours"] = {}
        return data


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


class EmployeeAssignSerializer(serializers.Serializer[Any]):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=RoleCode.choices)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_role(self, value: str) -> str:
        if value == RoleCode.CUSTOMER:
            raise serializers.ValidationError("An employee cannot be set to the customer role.")
        return value

    def validate_email(self, value: str) -> str:
        try:
            self._user = User.objects.get(email__iexact=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("No user found with this email.") from None
        if self._user.role != RoleCode.CUSTOMER or self._user.restaurant_id is not None:
            raise serializers.ValidationError(
                "This user is already staff. Update their role through the employee record."
            )
        return value

    @property
    def user(self) -> User:
        return self._user


class PublicRestaurantSettingsSerializer(serializers.ModelSerializer[RestaurantSettings]):
    working_hours = working_hours_field(read_only=True)

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
    working_hours = working_hours_field(required=False)

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
        read_only_fields = ["public_id", "rating", "created_at", "updated_at"]


class ZoneSerializer(serializers.ModelSerializer[Zone]):
    class Meta:
        model = Zone
        fields = [
            "public_id",
            "name",
            "sort_order",
            "edge_styles",
            "canvas_cols",
            "canvas_rows",
        ]
        read_only_fields = ["public_id"]


class TableSerializer(serializers.ModelSerializer[Table]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    zone = ZoneSerializer(read_only=True, allow_null=True)
    is_occupied = serializers.BooleanField(read_only=True)

    class Meta:
        model = Table
        fields = [
            "public_id",
            "restaurant",
            "public_number",
            "capacity",
            "is_occupied",
            "active",
            "zone",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "is_occupied", "created_at", "updated_at"]


class VerifyScanResponseSerializer(serializers.Serializer[None]):
    valid = serializers.BooleanField()
    detail = serializers.CharField()


class UpcomingReservationSerializer(serializers.Serializer[None]):
    public_id = serializers.UUIDField()
    table_id = serializers.UUIDField()
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()


class LayoutResponseSerializer(serializers.Serializer[None]):
    tables = TableSerializer(many=True)
    layout = serializers.JSONField(required=False, allow_null=True)
    upcoming_reservations = UpcomingReservationSerializer(many=True)
