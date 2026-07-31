from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.authentication.models import RoleCode, User
from apps.menu.services.localization import get_localized_content
from common.api import PublicIdRelatedField

from .models import (
    Restaurant,
    RestaurantSettings,
    RestaurantTranslation,
    Table,
    TableTranslation,
    Zone,
    ZoneTranslation,
    validate_working_hours,
)


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
    translations = serializers.SerializerMethodField()

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
            "translations",
            "created_at",
            "updated_at",
        ]
        # cover_image is uploaded via the dedicated `cover` action, so it is
        # read-only here (the profile PATCH ignores it).
        read_only_fields = ["public_id", "cover_image", "created_at", "updated_at"]

    def get_translations(self, obj: Restaurant) -> list[dict[str, str]]:
        return RestaurantTranslationSerializer(obj.translations.all(), many=True).data  # type: ignore[return-value]

    def to_representation(self, instance: Restaurant) -> dict[str, object]:
        data = super().to_representation(instance)
        try:
            data["working_hours"] = instance.settings.working_hours
            lang = getattr(self.context.get("request"), "active_language", None) or instance.settings.locale
        except RestaurantSettings.DoesNotExist:
            lang = "en"
        localized = get_localized_content(instance, lang)
        if "address" in localized:
            data["address"] = localized["address"]
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


class PublicRestaurantSettingsSerializer(serializers.ModelSerializer[RestaurantSettings]):
    working_hours = working_hours_field(read_only=True)

    class Meta:
        model = RestaurantSettings
        fields = ["currency", "timezone", "working_hours", "rating", "eta_min_minutes", "eta_max_minutes", "price_band"]
        read_only_fields = fields


class BookingSettingsSerializer(serializers.ModelSerializer[RestaurantSettings]):
    class Meta:
        model = RestaurantSettings
        fields = ["currency", "timezone", "working_hours", "supported_languages"]
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

    def to_representation(self, instance: Restaurant) -> dict[str, object]:
        data = super().to_representation(instance)
        try:
            lang = getattr(self.context.get("request"), "active_language", None) or instance.settings.locale
        except RestaurantSettings.DoesNotExist:
            lang = "en"
        localized = get_localized_content(instance, lang)
        if "address" in localized:
            data["address"] = localized["address"]
        return data


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
            "supported_languages",
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

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        locale = attrs.get("locale")
        supported = attrs.get("supported_languages")
        if supported is not None:
            for code in supported:
                if not isinstance(code, str) or not code.islower() or len(code) not in (2, 3):
                    raise serializers.ValidationError(
                        {"supported_languages": f"Invalid language code: {code!r}"}
                    )
            if not supported:
                raise serializers.ValidationError(
                    {"supported_languages": "At least one language must be configured"}
                )
            if locale is None:
                locale = self.instance.locale if self.instance else "en"
            if locale not in supported:
                raise serializers.ValidationError(
                    {"locale": "Default locale must be in supported_languages"}
                )
        if locale is not None and self.instance and locale != self.instance.locale:
            from apps.menu.services.localization import has_translations_for_locale

            if has_translations_for_locale(self.instance.restaurant_id, locale):
                raise serializers.ValidationError(
                    {
                        "locale": (
                            f"Cannot change locale to '{locale}' — one or more translations "
                            f"already exist for this language. Delete those translations first."
                        )
                    }
                )
        return attrs


class RestaurantTranslationSerializer(serializers.ModelSerializer[RestaurantTranslation]):
    class Meta:
        model = RestaurantTranslation
        fields = ["language_code", "address"]


class ZoneTranslationSerializer(serializers.ModelSerializer[ZoneTranslation]):
    class Meta:
        model = ZoneTranslation
        fields = ["language_code", "name"]


class TableTranslationSerializer(serializers.ModelSerializer[TableTranslation]):
    language_code = serializers.CharField(max_length=10)

    class Meta:
        model = TableTranslation
        fields = ["language_code", "public_number"]


class ZoneSerializer(serializers.ModelSerializer[Zone]):
    _lang = serializers.SerializerMethodField(read_only=True)
    _is_fallback = serializers.SerializerMethodField(read_only=True)
    translations = serializers.SerializerMethodField()

    class Meta:
        model = Zone
        fields = [
            "public_id",
            "name",
            "sort_order",
            "edge_styles",
            "canvas_cols",
            "canvas_rows",
            "_lang",
            "_is_fallback",
            "translations",
        ]
        read_only_fields = ["public_id"]

    def get_translations(self, obj: Zone) -> list[dict[str, str]]:
        return ZoneTranslationSerializer(obj.translations.all(), many=True).data  # type: ignore[return-value]

    def get__lang(self, obj: Zone) -> str | None:
        request = self.context.get("request")
        return getattr(request, "active_language", None) if request else None

    def get__is_fallback(self, obj: Zone) -> bool:
        request = self.context.get("request")
        return getattr(request, "active_language_is_fallback", False) if request else False

    def to_representation(self, instance: Zone) -> dict[str, Any]:
        data = super().to_representation(instance)
        request = self.context.get("request")
        lang = getattr(request, "active_language", None) if request else None
        if lang:
            localized = get_localized_content(instance, lang)
            if "name" in localized and localized["name"] is not None:
                data["name"] = localized["name"]
        return data


class TableSerializer(serializers.ModelSerializer[Table]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    zone = ZoneSerializer(read_only=True, allow_null=True)
    is_occupied = serializers.BooleanField(read_only=True)
    _lang = serializers.SerializerMethodField(read_only=True)
    _is_fallback = serializers.SerializerMethodField(read_only=True)
    translations = serializers.SerializerMethodField()

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
            "_lang",
            "_is_fallback",
            "translations",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "is_occupied", "created_at", "updated_at"]

    def get_translations(self, obj: Table) -> list[dict[str, str]]:
        return TableTranslationSerializer(obj.translations.all(), many=True).data  # type: ignore[return-value]

    def get__lang(self, obj: Table) -> str | None:
        request = self.context.get("request")
        return getattr(request, "active_language", None) if request else None

    def get__is_fallback(self, obj: Table) -> bool:
        request = self.context.get("request")
        return getattr(request, "active_language_is_fallback", False) if request else False

    def to_representation(self, instance: Table) -> dict[str, Any]:
        data = super().to_representation(instance)
        request = self.context.get("request")
        lang = getattr(request, "active_language", None) if request else None
        if lang:
            localized = get_localized_content(instance, lang)
            if "public_number" in localized and localized["public_number"] is not None:
                data["public_number"] = localized["public_number"]
        return data


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
