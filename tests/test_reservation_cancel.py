from collections.abc import Callable
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.authentication.models import RoleCode
from apps.orders.models import Session, SessionStatus
from apps.reservations.models import Reservation, ReservationStatus
from apps.reservations.services import cancel_reservation
from apps.restaurants.models import Restaurant, Table


@pytest.mark.django_db
def test_cancel_reservation_closes_its_open_session(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
) -> None:
    """Staff can cancel an ACTIVE (seated) reservation directly. If that
    reservation has an open session, cancelling must close it too — otherwise
    the table looks occupied forever afterward: get_unavailable_table_ids
    treats an open session as still-occupied and recomputes its grace cutoff
    from "now" on every check, so a dangling session never ages out.
    """
    customer = user_factory()
    customer.save()
    now = timezone.now()
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        customer=customer,
        table=table,
        guest_count=2,
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=1),
        status=ReservationStatus.ACTIVE,
    )
    session = Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=2,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=reservation.start_at,
    )

    cancel_reservation(reservation=reservation)

    reservation.refresh_from_db()
    session.refresh_from_db()
    assert reservation.status == ReservationStatus.CANCELLED
    assert session.status == SessionStatus.CLOSED


@pytest.mark.django_db
def test_cancel_pending_reservation_with_no_session_still_works(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
) -> None:
    """A PENDING reservation never has a session — cancelling it must not
    blow up looking for one that doesn't exist."""
    customer = user_factory()
    customer.save()
    start_at = timezone.now() + timedelta(hours=1)
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        customer=customer,
        table=table,
        guest_count=2,
        start_at=start_at,
        end_at=start_at + timedelta(hours=2),
        status=ReservationStatus.PENDING,
    )

    cancel_reservation(reservation=reservation)

    reservation.refresh_from_db()
    assert reservation.status == ReservationStatus.CANCELLED


@pytest.mark.django_db(databases=["default"], transaction=True)
def test_cancel_active_reservation_emits_table_freed_and_cancelled_events(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
) -> None:
    """Cancelling a seated (ACTIVE) reservation closes its session — the
    table goes from occupied to free right now, not just "eventually" via
    the next availability check. Without HALL_TABLE_STATUS_CHANGED, the
    customer floor stream and staff hall dashboard both stay stale until a
    reload, undercutting the whole point of a real-time floor.
    """
    customer = user_factory()
    customer.save()
    staff = user_factory(role=RoleCode.WAITER)
    staff.save()
    now = timezone.now()
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        customer=customer,
        table=table,
        guest_count=2,
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=1),
        status=ReservationStatus.ACTIVE,
    )
    session = Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=2,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=reservation.start_at,
    )

    with (
        patch("apps.reservations.services.emit_hall_table_status_changed") as mock_status,
        patch("apps.reservations.services.emit_hall_reservation_cancelled") as mock_cancelled,
    ):
        cancel_reservation(reservation=reservation, actor=staff)

    mock_status.assert_called_once()
    status_kwargs = mock_status.call_args[1]
    assert status_kwargs["table_id"] == str(table.public_id)
    assert status_kwargs["previous_status"] == "occupied"
    assert status_kwargs["current_status"] == "free"
    assert status_kwargs["session_id"] == str(session.public_id)
    assert status_kwargs["actor"] == staff

    mock_cancelled.assert_called_once()
    cancelled_kwargs = mock_cancelled.call_args[1]
    assert cancelled_kwargs["reservation_id"] == str(reservation.public_id)
    assert cancelled_kwargs["table_id"] == str(table.public_id)
    assert cancelled_kwargs["actor"] == staff


@pytest.mark.django_db(databases=["default"], transaction=True)
def test_cancel_pending_reservation_emits_only_cancelled_event(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
) -> None:
    """A PENDING reservation never has a session, so there's no table-freed
    event to send — but HALL_RESERVATION_CANCELLED still fires, so the
    customer floor drops it from "upcoming" and refreshes slot availability.
    """
    customer = user_factory()
    customer.save()
    staff = user_factory(role=RoleCode.WAITER)
    staff.save()
    start_at = timezone.now() + timedelta(hours=1)
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        customer=customer,
        table=table,
        guest_count=2,
        start_at=start_at,
        end_at=start_at + timedelta(hours=2),
        status=ReservationStatus.PENDING,
    )

    with (
        patch("apps.reservations.services.emit_hall_table_status_changed") as mock_status,
        patch("apps.reservations.services.emit_hall_reservation_cancelled") as mock_cancelled,
    ):
        cancel_reservation(reservation=reservation, actor=staff)

    mock_status.assert_not_called()
    mock_cancelled.assert_called_once()
    cancelled_kwargs = mock_cancelled.call_args[1]
    assert cancelled_kwargs["reservation_id"] == str(reservation.public_id)
    assert cancelled_kwargs["actor"] == staff


@pytest.mark.django_db
def test_cancel_reservation_without_actor_skips_events(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
) -> None:
    """Matches create_reservation's convention: actor is optional, and
    omitting it just skips the notification rather than erroring."""
    customer = user_factory()
    customer.save()
    start_at = timezone.now() + timedelta(hours=1)
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        customer=customer,
        table=table,
        guest_count=2,
        start_at=start_at,
        end_at=start_at + timedelta(hours=2),
        status=ReservationStatus.PENDING,
    )

    with (
        patch("apps.reservations.services.emit_hall_table_status_changed") as mock_status,
        patch("apps.reservations.services.emit_hall_reservation_cancelled") as mock_cancelled,
    ):
        cancel_reservation(reservation=reservation)

    mock_status.assert_not_called()
    mock_cancelled.assert_not_called()
