from typing import Any

from django.db import transaction

from apps.authentication.models import User

from .models import Restaurant, RestaurantSettings

RESTAURANT_UPDATABLE = frozenset(
    {"name", "address", "phone", "telegram_url", "facebook_url"}
)
SETTINGS_UPDATABLE = frozenset(
    {
        "timezone",
        "currency",
        "locale",
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
        employee.save(update_fields=changed)
    return employee


__all__ = [
    "update_restaurant",
    "update_restaurant_settings",
    "manage_employee",
]
