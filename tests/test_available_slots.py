from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from apps.orders.models import Session, SessionStatus
from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import Restaurant, RestaurantSettings, Table

KYIV = ZoneInfo("Europe/Kyiv")
UTC = ZoneInfo("UTC")

AVAILABLE_SLOTS_URL = "/api/reservations/reservations/available-slots/"


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
