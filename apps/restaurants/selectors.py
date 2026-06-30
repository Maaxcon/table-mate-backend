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


_DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]  # Monday=0 .. Sunday=6


def _hhmm_to_minutes(value: object) -> int | None:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        return None
    hh, mm = value[:2], value[3:]
    if not hh.isdigit() or not mm.isdigit():
        return None
    return int(hh) * 60 + int(mm)


def is_restaurant_open(restaurant_id: int, when: datetime_cls | None = None) -> bool:
    """Whether the restaurant is open at `when` (default now) per its working hours.

    No settings or no configured hours → treated as open (don't block). Once hours
    are configured they are authoritative: a day with no usable open/close window —
    whether its entry is missing or unparseable — is closed. Supports overnight
    windows (close < open).
    """
    settings = get_restaurant_settings(restaurant_id)
    if settings is None:
        return True
    working_hours = settings.working_hours or {}
    if not working_hours:
        return True

    tz = ZoneInfo(settings.timezone) if settings.timezone else ZoneInfo("UTC")
    local = (when or timezone.now()).astimezone(tz)
    hours = working_hours.get(_DAY_KEYS[local.weekday()])
    if not isinstance(hours, dict):
        return False

    open_min = _hhmm_to_minutes(hours.get("open"))
    close_min = _hhmm_to_minutes(hours.get("close"))
    if open_min is None or close_min is None:
        return False  # configured day with unreadable hours — treat as closed

    now_min = local.hour * 60 + local.minute
    if close_min > open_min:
        return open_min <= now_min < close_min
    return now_min >= open_min or now_min < close_min  # overnight window


def list_employees(restaurant_id: int) -> QuerySet[User]:
    return User.objects.filter(restaurant_id=restaurant_id).exclude(role=RoleCode.CUSTOMER).order_by("role", "email")


def get_employee(employee_id: str, restaurant_id: int) -> User | None:
    return (
        User.objects.filter(public_id=employee_id, restaurant_id=restaurant_id).exclude(role=RoleCode.CUSTOMER).first()
    )


def get_tables_with_occupancy(restaurant_id: int) -> QuerySet[Table]:
    qs = Table.objects.select_related("zone").filter(restaurant_id=restaurant_id, active=True)
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
    end_at: Any
    customer_name: Any
    guest_count: Any


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
        start_at__lte=today_end,
    ).select_related("table", "customer")

    upcoming: list[_UpcomingReservation] = [
        {
            "public_id": r.public_id,
            "table_id": r.table.public_id,
            "start_at": r.start_at,
            "end_at": r.end_at,
            "customer_name": (r.customer.get_full_name() or r.customer.email) if r.customer else "Guest",
            "guest_count": r.guest_count,
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
