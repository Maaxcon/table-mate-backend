from datetime import datetime, timedelta
from datetime import time as time_type
from zoneinfo import ZoneInfo

from django.db import models as dm
from django.db.models import QuerySet

from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import RestaurantSettings, Table


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

    current_time = local_dt.time()

    if day_config:
        open_time = _parse_time(day_config.get("open", "00:00"))
        close_time = _parse_time(day_config.get("close", "23:59"))

        if open_time <= close_time:
            if open_time <= current_time <= close_time:
                return True
        else:
            if current_time >= open_time or current_time <= close_time:
                return True

    if current_time <= time_type(hour=12, minute=0):
        prev_day_name = (local_dt - timedelta(days=1)).strftime("%A").lower()
        prev_config = working_hours.get(prev_day_name)
        if prev_config:
            prev_open = _parse_time(prev_config.get("open", "00:00"))
            prev_close = _parse_time(prev_config.get("close", "23:59"))
            if prev_open > prev_close and current_time <= prev_close:
                return True

    return False


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
    ).exclude(id__in=dm.Subquery(overlapping))

    if guest_count is not None:
        qs = qs.filter(capacity__gte=guest_count)

    return qs
