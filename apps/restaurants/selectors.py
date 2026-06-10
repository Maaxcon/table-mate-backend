from django.db.models import QuerySet

from apps.authentication.models import RoleCode, User

from .models import Restaurant, RestaurantSettings


def get_restaurant(restaurant_id: int) -> Restaurant | None:
    return Restaurant.objects.filter(id=restaurant_id).first()


def get_restaurant_settings(restaurant_id: int) -> RestaurantSettings | None:
    return RestaurantSettings.objects.filter(restaurant_id=restaurant_id).first()


def list_employees(restaurant_id: int) -> QuerySet[User]:
    return (
        User.objects.filter(restaurant_id=restaurant_id)
        .exclude(role=RoleCode.CUSTOMER)
        .order_by("role", "email")
    )


def get_employee(employee_id: str, restaurant_id: int) -> User | None:
    return (
        User.objects.filter(public_id=employee_id, restaurant_id=restaurant_id)
        .exclude(role=RoleCode.CUSTOMER)
        .first()
    )


__all__ = [
    "get_restaurant",
    "get_restaurant_settings",
    "list_employees",
    "get_employee",
]
