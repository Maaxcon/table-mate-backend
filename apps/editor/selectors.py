from datetime import datetime, timedelta
from datetime import time as time_type
from zoneinfo import ZoneInfo

from django.db import models as dm
from django.db.models import OuterRef, QuerySet, Subquery
from django.db.models.functions import Coalesce, Greatest

from apps.orders.models import Session, SessionStatus
from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import RestaurantSettings, Table
from apps.restaurants.selectors import _DAY_KEYS


def _parse_time(value: str) -> time_type:
    parts = value.split(":")
    return time_type(hour=int(parts[0]), minute=int(parts[1]))


def is_within_working_hours(settings: RestaurantSettings, dt: datetime) -> bool:
    working_hours = settings.working_hours
    if not working_hours:
        return True

    tz = ZoneInfo(settings.timezone)
    local_dt = dt.astimezone(tz)

    day_name = _DAY_KEYS[local_dt.weekday()]
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
        prev_day_name = _DAY_KEYS[(local_dt - timedelta(days=1)).weekday()]
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
    current_reservation_id: int | None = None,
) -> QuerySet[Table]:
    settings = RestaurantSettings.objects.filter(restaurant_id=restaurant_id).first()

    if settings and not is_within_working_hours(settings, start_at):
        return Table.objects.none()

    if settings and not is_within_working_hours(settings, end_at):
        return Table.objects.none()

    active_session_subquery = (
        Session.objects.filter(
            reservation=OuterRef("pk"),
            status=SessionStatus.OPEN,
        )
        .order_by("opened_at")
        .values("opened_at")[:1]
    )

    reservations = Reservation.objects.filter(
        restaurant_id=restaurant_id,
        status__in=[ReservationStatus.PENDING, ReservationStatus.ACTIVE],
    ).annotate(effective_start=Greatest("start_at", Coalesce(Subquery(active_session_subquery), "start_at")))

    overlapping = reservations.filter(
        effective_start__lt=end_at,
        end_at__gt=start_at,
    )
    if current_reservation_id is not None:
        overlapping = overlapping.exclude(id=current_reservation_id)
    overlapping_table_ids = overlapping.values("table_id")

    qs = Table.objects.filter(
        restaurant_id=restaurant_id,
        active=True,
    ).exclude(id__in=dm.Subquery(overlapping_table_ids))

    if guest_count is not None:
        qs = qs.filter(capacity__gte=guest_count)

    return qs
