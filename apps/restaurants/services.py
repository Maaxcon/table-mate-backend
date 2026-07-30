from typing import Any

from django.conf import settings as django_settings
from django.db import transaction

from apps.authentication.models import User

from .models import Restaurant, RestaurantSettings, RestaurantTranslation, Table, TableTranslation, ZoneTranslation

RESTAURANT_UPDATABLE = frozenset({"name", "address", "phone", "telegram_url", "facebook_url"})
SETTINGS_UPDATABLE = frozenset(
    {
        "timezone",
        "currency",
        "locale",
        "supported_languages",
        "default_tax_rate",
        "default_service_charge",
        "working_hours",
        "eta_min_minutes",
        "eta_max_minutes",
        "price_band",
    }
)
EMPLOYEE_UPDATABLE = frozenset({"role", "is_active", "first_name", "last_name", "phone"})


def _apply_fields(instance: Any, data: dict[str, Any], allowed: frozenset[str]) -> list[str]:
    """Set only allowed fields that are present in data. Return changed field names."""
    changed = [field for field in allowed if field in data]
    for field in changed:
        setattr(instance, field, data[field])
    return changed


@transaction.atomic
def update_restaurant(restaurant: Restaurant, **data: Any) -> Restaurant:
    changed = _apply_fields(restaurant, data, RESTAURANT_UPDATABLE)
    if changed:
        restaurant.save(update_fields=[*changed, "updated_at"])
    return restaurant


@transaction.atomic
def update_restaurant_settings(settings: RestaurantSettings, **data: Any) -> RestaurantSettings:
    changed = _apply_fields(settings, data, SETTINGS_UPDATABLE)
    if changed:
        settings.save(update_fields=[*changed, "updated_at"])
    return settings


@transaction.atomic
def manage_employee(employee: User, **data: Any) -> User:
    """Update an existing employee (role, active state, profile fields)."""
    changed = _apply_fields(employee, data, EMPLOYEE_UPDATABLE)
    if changed:
        employee.save(update_fields=[*changed, "updated_at"])
    return employee


@transaction.atomic
def create_employee(*, restaurant_id: int, email: str, role: str, **data: Any) -> User:
    """Create a staff account tied to the admin's restaurant.

    The restaurant is always supplied by the caller (from the admin's auth
    context), never trusted from the request body, so an admin can only add
    staff to their own restaurant. The account has no usable password — the
    employee signs in with Google using the same email.
    """
    return User.objects.create_user(
        email=email,
        role=role,
        restaurant_id=restaurant_id,
        first_name=data.get("first_name", ""),
        last_name=data.get("last_name", ""),
        phone=data.get("phone"),
    )


def build_table_menu_url(table: Table) -> str:
    """Menu deep link a table's QR code encodes.

    Opens the table's restaurant menu with the table pre-selected, so a scan
    skips the manual restaurant/table lookup the menu page otherwise needs.
    """
    return f"{django_settings.FRONTEND_BASE_URL}/menu/{table.restaurant.public_id}?table={table.public_id}"


def create_restaurant_translation(*, restaurant_id: int, language_code: str, address: str) -> RestaurantTranslation:
    return RestaurantTranslation.objects.create(
        restaurant_id=restaurant_id,
        language_code=language_code,
        address=address,
    )


def update_restaurant_translation(*, restaurant_id: int, language_code: str, address: str) -> RestaurantTranslation:
    translation = RestaurantTranslation.objects.get(restaurant_id=restaurant_id, language_code=language_code)
    translation.address = address
    translation.save(update_fields=["address", "updated_at"])
    return translation


def delete_restaurant_translation(*, restaurant_id: int, language_code: str) -> None:
    RestaurantTranslation.objects.filter(restaurant_id=restaurant_id, language_code=language_code).delete()


def get_restaurant_translations(*, restaurant_id: int) -> list[RestaurantTranslation]:
    return list(RestaurantTranslation.objects.filter(restaurant_id=restaurant_id))


def create_zone_translation(*, zone_id: int, language_code: str, name: str) -> ZoneTranslation:
    return ZoneTranslation.objects.create(
        zone_id=zone_id,
        language_code=language_code,
        name=name,
    )


def update_zone_translation(*, zone_id: int, language_code: str, name: str) -> ZoneTranslation:
    translation = ZoneTranslation.objects.get(zone_id=zone_id, language_code=language_code)
    translation.name = name
    translation.save(update_fields=["name", "updated_at"])
    return translation


def delete_zone_translation(*, zone_id: int, language_code: str) -> None:
    ZoneTranslation.objects.filter(zone_id=zone_id, language_code=language_code).delete()


def get_zone_translations(*, zone_id: int) -> list[ZoneTranslation]:
    return list(ZoneTranslation.objects.filter(zone_id=zone_id))


def create_table_translation(*, table_id: int, language_code: str, public_number: str) -> TableTranslation:
    return TableTranslation.objects.create(
        table_id=table_id,
        language_code=language_code,
        public_number=public_number,
    )


def update_table_translation(*, table_id: int, language_code: str, public_number: str) -> TableTranslation:
    translation = TableTranslation.objects.get(table_id=table_id, language_code=language_code)
    translation.public_number = public_number
    translation.save(update_fields=["public_number", "updated_at"])
    return translation


def delete_table_translation(*, table_id: int, language_code: str) -> None:
    TableTranslation.objects.filter(table_id=table_id, language_code=language_code).delete()


def get_table_translations(*, table_id: int) -> list[TableTranslation]:
    return list(TableTranslation.objects.filter(table_id=table_id))


__all__ = [
    "update_restaurant",
    "update_restaurant_settings",
    "manage_employee",
    "create_employee",
    "build_table_menu_url",
    "create_restaurant_translation",
    "update_restaurant_translation",
    "delete_restaurant_translation",
    "get_restaurant_translations",
    "create_zone_translation",
    "update_zone_translation",
    "delete_zone_translation",
    "get_zone_translations",
    "create_table_translation",
    "update_table_translation",
    "delete_table_translation",
    "get_table_translations",
]
