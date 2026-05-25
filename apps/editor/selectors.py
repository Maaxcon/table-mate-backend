from datetime import datetime
from datetime import time as time_type
from zoneinfo import ZoneInfo

from django.db import models as dm
from django.db.models import QuerySet

from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import RestaurantSettings, Table, TableStatus


def _parse_time(value: str) -> time_type:
    parts = value.split(":")
    return time_type(hour=int(parts[0]), minute=int(parts[1]))


def is_within_working_hours(settings: RestaurantSettings, dt: datetime) -> bool:
    working_hours = settings.working_hours
    if not working_hours:
        return True

    tz = ZoneInfo(settings.timezone)
    local_dt = dt.astimezone(tz)

    day_name = local_dt.strftime("%A").lower()
    day_config = working_hours.get(day_name)
    if not day_config:
        return False

    current_time = local_dt.time()
    open_time = _parse_time(day_config.get("open", "00:00"))
    close_time = _parse_time(day_config.get("close", "23:59"))

    if open_time <= close_time:
        return open_time <= current_time <= close_time
    return current_time >= open_time or current_time <= close_time


def get_available_tables(
    restaurant_id: int,
    start_at: datetime,
    end_at: datetime,
    guest_count: int | None = None,
) -> QuerySet[Table]:
    settings = RestaurantSettings.objects.filter(restaurant_id=restaurant_id).first()

    if settings and not is_within_working_hours(settings, start_at):
        return Table.objects.none()

    if settings and not is_within_working_hours(settings, end_at):
        return Table.objects.none()

    overlapping = Reservation.objects.filter(
        restaurant_id=restaurant_id,
        status=ReservationStatus.CONFIRMED,
        start_at__lt=end_at,
        end_at__gt=start_at,
    ).values("table_id")

    qs = Table.objects.filter(
        restaurant_id=restaurant_id,
        active=True,
        status=TableStatus.FREE,
    ).exclude(id__in=dm.Subquery(overlapping))

    if guest_count is not None:
        qs = qs.filter(capacity__gte=guest_count)

    return qs
