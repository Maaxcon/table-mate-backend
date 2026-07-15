from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.orders.models import Session, SessionStatus
from apps.reservations.models import Reservation, ReservationStatus
from apps.reservations.selectors import get_unavailable_table_ids
from apps.restaurants.models import Restaurant, Table
from apps.restaurants.selectors import get_tables_with_occupancy


def _seated_reservation(
    restaurant: Restaurant,
    table: Table,
    customer: Any,
    now: Any,
    *,
    session_end_offset: timedelta | None = None,
) -> Reservation:
    """An active reservation with an open session — a party currently seated,
    booked end 5 minutes from now (soon overstaying)."""
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        customer=customer,
        table=table,
        guest_count=2,
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(minutes=5),
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
        ends_at=now + session_end_offset if session_end_offset is not None else reservation.end_at,
    )
    return reservation


@pytest.mark.django_db
def test_session_grace_period_is_fixed_not_duration_scaled(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
) -> None:
    """A table with a currently open session must read the same
    available/unavailable for the same start time regardless of how long the
    NEW booking being checked wants to be — the table's physical occupancy
    doesn't depend on a prospective guest's requested duration. Previously
    the grace period was `end_at - start_at` (the query's own window), so a
    short check and a long check at the identical start time could disagree.
    """
    customer = user_factory()
    customer.save()
    now = timezone.now()
    _seated_reservation(restaurant, table, customer, now)

    # 90 minutes out: past the fixed 30-min grace window, but well inside
    # what a duration-scaled grace period (e.g. a 4-hour booking) would have
    # blocked under the old behavior.
    slot_start = now + timedelta(minutes=90)

    short_unavailable = get_unavailable_table_ids(
        restaurant_id=restaurant.id,
        start_at=slot_start,
        end_at=slot_start + timedelta(minutes=60),
        table_ids=[table.pk],
        now=now,
    )
    long_unavailable = get_unavailable_table_ids(
        restaurant_id=restaurant.id,
        start_at=slot_start,
        end_at=slot_start + timedelta(minutes=240),
        table_ids=[table.pk],
        now=now,
    )

    assert table.pk not in short_unavailable
    assert table.pk not in long_unavailable


@pytest.mark.django_db
def test_session_grace_period_blocks_near_term_slot_regardless_of_duration(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
) -> None:
    """Within the fixed grace window, the table stays blocked no matter how
    short the requested duration is."""
    customer = user_factory()
    customer.save()
    now = timezone.now()
    _seated_reservation(restaurant, table, customer, now)

    slot_start = now + timedelta(minutes=10)  # inside the 30-min grace window

    short_unavailable = get_unavailable_table_ids(
        restaurant_id=restaurant.id,
        start_at=slot_start,
        end_at=slot_start + timedelta(minutes=30),
        table_ids=[table.pk],
        now=now,
    )

    assert table.pk in short_unavailable


@pytest.mark.django_db
def test_dangling_open_session_on_cancelled_reservation_does_not_block_table(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
) -> None:
    """A session left OPEN after its reservation was cancelled (a
    data-integrity bug elsewhere, not a normal state — see
    cancel_reservation, which now closes it) must not make the table look
    permanently occupied. Without this guard the grace cutoff recomputes to
    "now + 30min" on every single check forever, since a cancelled
    reservation's end_at never arrives to age it out.
    """
    customer = user_factory()
    customer.save()
    now = timezone.now()
    reservation = _seated_reservation(restaurant, table, customer, now)
    reservation.status = ReservationStatus.CANCELLED
    reservation.save(update_fields=["status"])
    # The session itself is untouched — still OPEN, exactly the dangling
    # state a missed cleanup path would leave behind.

    unavailable = get_unavailable_table_ids(
        restaurant_id=restaurant.id,
        start_at=now + timedelta(minutes=10),
        end_at=now + timedelta(minutes=40),
        table_ids=[table.pk],
        now=now,
    )

    assert table.pk not in unavailable


@pytest.mark.django_db
def test_extended_session_end_keeps_table_blocked_past_booked_end(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
) -> None:
    customer = user_factory()
    customer.save()
    now = timezone.now()
    _seated_reservation(
        restaurant,
        table,
        customer,
        now,
        session_end_offset=timedelta(hours=2),
    )

    unavailable = get_unavailable_table_ids(
        restaurant_id=restaurant.id,
        start_at=now + timedelta(minutes=80),
        end_at=now + timedelta(minutes=110),
        table_ids=[table.pk],
        now=now,
    )

    assert table.pk in unavailable


@pytest.mark.django_db
def test_floor_table_selector_reports_prolonged_session_occupied(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
) -> None:
    customer = user_factory()
    customer.save()
    now = timezone.now()
    reservation = _seated_reservation(restaurant, table, customer, now)
    reservation.end_at = now - timedelta(minutes=5)
    reservation.save(update_fields=["end_at"])

    session = Session.objects.get(reservation=reservation, status=SessionStatus.OPEN)
    session.ends_at = now + timedelta(minutes=30)
    session.save(update_fields=["ends_at"])

    occupied = list(get_tables_with_occupancy(restaurant.id))

    assert len(occupied) == 1
    assert occupied[0].pk == table.pk
    assert occupied[0].is_occupied is True
