from typing import Any

from django.conf import settings as django_settings
from django.db import transaction

from apps.authentication.models import RoleCode, User

from .models import Restaurant, RestaurantSettings, Table

RESTAURANT_UPDATABLE = frozenset({"name", "address", "phone", "telegram_url", "facebook_url"})
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


@transaction.atomic
def assign_employee(*, user: User, restaurant_id: int, role: str) -> User:
    user.role = role
    user.restaurant_id = restaurant_id
    user.save(update_fields=["role", "restaurant_id", "updated_at"])
    return user


@transaction.atomic
def remove_employee(employee: User) -> User:
    """Demote a staff member back to a regular customer account.

    The user row is preserved so the account can keep signing in as a customer;
    only the role and restaurant binding are cleared. The role-change signal
    bumps token_version, so the staff user's active sessions are invalidated
    immediately.
    """
    employee.role = RoleCode.CUSTOMER
    employee.restaurant_id = None
    employee.save(update_fields=["role", "restaurant_id", "updated_at"])
    return employee


def build_table_menu_url(table: Table) -> str:
    """Menu deep link a table's QR code encodes.

    Opens the table's restaurant menu with the table pre-selected, so a scan
    skips the manual restaurant/table lookup the menu page otherwise needs.
    """
    return f"{django_settings.FRONTEND_BASE_URL}/menu/{table.restaurant.public_id}?table={table.public_id}"


__all__ = [
    "update_restaurant",
    "update_restaurant_settings",
    "manage_employee",
    "create_employee",
    "assign_employee",
    "remove_employee",
    "build_table_menu_url",
]
