from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from apps.orders.models import Session, SessionStatus
from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import Restaurant, RestaurantSettings, Table
from apps.restaurants.selectors import _DAY_KEYS

KYIV = ZoneInfo("Europe/Kyiv")
UTC = ZoneInfo("UTC")

AVAILABLE_SLOTS_URL = "/api/reservations/reservations/available-slots/"
AVAILABILITY_URL = "/api/reservations/reservations/availability/"


@pytest.mark.django_db
def test_available_slots_excludes_own_session_from_grace_cutoff(
    restaurant: Restaurant,
    table: Table,
    restaurant_settings: RestaurantSettings,
    user_factory: Callable[..., Any],
    api_client: Any,
) -> None:
    """A waiter opens ModifyReservationModal for a guest who's overstaying
    (booked end already passed, still ACTIVE with an open session) and asks
    for available slots to push the end out. The endpoint excludes the
    reservation from the overlap query via ?exclude=, but the session grace
    cutoff was computed with no exclusion at all — the ACTIVE reservation's
    own open session then self-blocks the near-term slots the modal actually
    needs, even though reschedule_reservation itself would accept them (it
    passes current_reservation_id and excludes both the overlap and the
    session). Frozen "now" not on a 30-min boundary (12:05, not 12:00) so the
    next candidate slot (12:30) falls strictly inside the buggy now+30
    window, reproducing the bug precisely instead of missing it by luck.
    """
    customer = user_factory()
    customer.save()

    today_kyiv = datetime.now(KYIV).date()
    fixed_now = datetime(today_kyiv.year, today_kyiv.month, today_kyiv.day, 12, 5, tzinfo=KYIV).astimezone(UTC)

    reservation = Reservation.objects.create(
        restaurant=restaurant,
        customer=customer,
        table=table,
        guest_count=2,
        start_at=fixed_now - timedelta(hours=2),
        end_at=fixed_now - timedelta(hours=1),  # already passed -> overstaying
        status=ReservationStatus.ACTIVE,
    )
    Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=2,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=reservation.start_at,
    )

    with patch("apps.reservations.views.timezone.now", return_value=fixed_now):
        resp = api_client.get(
            AVAILABLE_SLOTS_URL,
            {
                "table": str(table.public_id),
                "date": today_kyiv.isoformat(),
                "exclude": str(reservation.public_id),
            },
        )

    assert resp.status_code == 200
    slots = resp.json()[today_kyiv.isoformat()]
    assert "12:30" in slots


@pytest.mark.django_db
def test_available_slots_without_exclude_still_blocks_others_sessions(
    restaurant: Restaurant,
    table: Table,
    restaurant_settings: RestaurantSettings,
    user_factory: Callable[..., Any],
    api_client: Any,
) -> None:
    """Sanity check for the fix's other direction: an open session that
    genuinely isn't excluded must still block near-term slots — the fix only
    exempts the caller's own excluded reservation, not sessions in general.
    """
    customer = user_factory()
    customer.save()

    today_kyiv = datetime.now(KYIV).date()
    fixed_now = datetime(today_kyiv.year, today_kyiv.month, today_kyiv.day, 12, 5, tzinfo=KYIV).astimezone(UTC)

    reservation = Reservation.objects.create(
        restaurant=restaurant,
        customer=customer,
        table=table,
        guest_count=2,
        start_at=fixed_now - timedelta(hours=2),
        end_at=fixed_now - timedelta(hours=1),
        status=ReservationStatus.ACTIVE,
    )
    Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=2,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=reservation.start_at,
    )

    with patch("apps.reservations.views.timezone.now", return_value=fixed_now):
        resp = api_client.get(
            AVAILABLE_SLOTS_URL,
            {"table": str(table.public_id), "date": today_kyiv.isoformat()},
        )

    assert resp.status_code == 200
    slots = resp.json()[today_kyiv.isoformat()]
    assert "12:30" not in slots


@pytest.mark.django_db
def test_available_slots_and_availability_agree_at_a_misaligned_closing_tail(
    restaurant: Restaurant,
    table: Table,
    restaurant_settings: RestaurantSettings,
    api_client: Any,
) -> None:
    """available-slots must never list a start time that availability would
    then reject as "too close to closing" for the exact same instant — a
    close time that isn't 30-min-aligned (22:40, not 22:00 or 22:30) used to
    break that invariant: available-slots only checked the slot started
    before close, while availability required at least 30 min left, so the
    grid could offer a slot that 409s (or availability could report a table
    free/taken for a time the grid never listed at all).
    """
    target_date = (datetime.now(KYIV) + timedelta(days=7)).date()
    day_key = _DAY_KEYS[target_date.weekday()]
    restaurant_settings.working_hours = {
        **restaurant_settings.working_hours,
        day_key: {"open": "10:00", "close": "22:40"},
    }
    restaurant_settings.save(update_fields=["working_hours"])

    slots_resp = api_client.get(
        AVAILABLE_SLOTS_URL,
        {"table": str(table.public_id), "date": target_date.isoformat()},
    )
    assert slots_resp.status_code == 200
    slots = slots_resp.json()[target_date.isoformat()]

    # 22:00 leaves exactly 40 min before the 22:40 close -> still bookable.
    assert "22:00" in slots
    # 22:30 would leave only 10 min -> available-slots must not offer it...
    assert "22:30" not in slots

    # ...and availability must agree it's not bookable either, for the same time.
    avail_resp = api_client.get(
        AVAILABILITY_URL,
        {
            "restaurant": str(restaurant.public_id),
            "date": target_date.isoformat(),
            "time": "22:30",
            "duration": 30,
        },
    )
    assert avail_resp.status_code == 200
    assert avail_resp.json()["availability"][str(table.public_id)] is False

    # And it must agree 22:00 (the last slot available-slots did offer) is bookable.
    avail_resp_ok = api_client.get(
        AVAILABILITY_URL,
        {
            "restaurant": str(restaurant.public_id),
            "date": target_date.isoformat(),
            "time": "22:00",
            "duration": 30,
        },
    )
    assert avail_resp_ok.status_code == 200
    assert avail_resp_ok.json()["availability"][str(table.public_id)] is True


@pytest.mark.django_db
def test_available_slots_filters_past_slots_on_an_explicitly_queried_past_date(
    restaurant: Restaurant,
    table: Table,
    restaurant_settings: RestaurantSettings,
    api_client: Any,
) -> None:
    """The past-slot filter used to only apply when the queried date exactly
    equaled the server's "today" (`d == today_local`) — so a date explicitly
    queried while it's already yesterday (relevant right after midnight, for
    a still-open overnight session that started the night before) skipped
    the filter entirely and returned every slot on that day, including ones
    from many hours in the past. The filter must key off the absolute instant
    (slot_utc <= now_utc), not day equality.
    """
    today_kyiv = datetime.now(KYIV).date()
    yesterday = today_kyiv - timedelta(days=1)
    day_key = _DAY_KEYS[yesterday.weekday()]
    restaurant_settings.working_hours = {
        **restaurant_settings.working_hours,
        day_key: {"open": "10:00", "close": "20:00"},
    }
    restaurant_settings.save(update_fields=["working_hours"])
    fixed_now = datetime(today_kyiv.year, today_kyiv.month, today_kyiv.day, 8, 0, tzinfo=KYIV).astimezone(UTC)

    with patch("apps.reservations.views.timezone.now", return_value=fixed_now):
        resp = api_client.get(
            AVAILABLE_SLOTS_URL,
            {"table": str(table.public_id), "date": yesterday.isoformat()},
        )

    assert resp.status_code == 200
    # Yesterday's entire 10:00-20:00 window is in the past relative to
    # 08:00 today -> nothing should be offered.
    assert resp.json()[yesterday.isoformat()] == []
