from datetime import datetime as datetime_cls
from typing import Any, TypedDict
from zoneinfo import ZoneInfo

from django.db.models import Exists, OuterRef, QuerySet
from django.utils import timezone

from apps.authentication.models import RoleCode, User
from apps.orders.models import Session, SessionStatus
from apps.reservations.models import Reservation, ReservationStatus

from .models import Restaurant, RestaurantSettings, Table


def get_restaurant(restaurant_id: int) -> Restaurant | None:
    return Restaurant.objects.filter(id=restaurant_id).first()


def get_restaurant_settings(restaurant_id: int) -> RestaurantSettings | None:
    return RestaurantSettings.objects.filter(restaurant_id=restaurant_id).first()


def list_employees(restaurant_id: int) -> QuerySet[User]:
    return User.objects.filter(restaurant_id=restaurant_id).exclude(role=RoleCode.CUSTOMER).order_by("role", "email")


def get_employee(employee_id: str, restaurant_id: int) -> User | None:
    return (
        User.objects.filter(public_id=employee_id, restaurant_id=restaurant_id).exclude(role=RoleCode.CUSTOMER).first()
    )


def get_tables_with_occupancy(restaurant_id: int) -> QuerySet[Table]:
    qs = Table.objects.select_related("zone").filter(restaurant_id=restaurant_id)
    occupied_subquery = Session.objects.filter(
        table=OuterRef("pk"),
        status=SessionStatus.OPEN,
        reservation__status=ReservationStatus.ACTIVE,
    )
    return qs.annotate(is_occupied=Exists(occupied_subquery))


class _UpcomingReservation(TypedDict):
    public_id: Any
    table_id: Any
    start_at: Any


class LayoutData(TypedDict):
    upcoming_reservations: list[_UpcomingReservation]


def get_layout_data(restaurant_id: int) -> LayoutData:
    now = timezone.now()

    settings = RestaurantSettings.objects.filter(restaurant_id=restaurant_id).first()
    tz = ZoneInfo(settings.timezone) if settings else ZoneInfo("UTC")
    today_local = now.astimezone(tz).date()
    today_end_local = datetime_cls(
        today_local.year,
        today_local.month,
        today_local.day,
        23,
        59,
        59,
        999999,
        tzinfo=tz,
    )
    today_end = today_end_local.astimezone(ZoneInfo("UTC"))

    reservations = Reservation.objects.filter(
        restaurant_id=restaurant_id,
        status=ReservationStatus.PENDING,
        start_at__gte=now,
        start_at__lte=today_end,
    ).select_related("table")

    upcoming: list[_UpcomingReservation] = [
        {
            "public_id": r.public_id,
            "table_id": r.table.public_id,
            "start_at": r.start_at,
        }
        for r in reservations
        if r.table is not None
    ]
    return {"upcoming_reservations": upcoming}


__all__ = [
    "get_employee",
    "get_layout_data",
    "get_restaurant",
    "get_restaurant_settings",
    "get_tables_with_occupancy",
    "list_employees",
]
