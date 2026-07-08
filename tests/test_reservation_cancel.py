from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

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
