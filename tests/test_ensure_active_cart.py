import concurrent.futures
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.db import connection
from django.utils import timezone

from apps.authentication.models import RoleCode
from apps.orders.models import CartSession, CartSessionStatus, Session, SessionStatus
from apps.orders.services import ensure_active_cart_for_table
from apps.reservations.models import (
    Reservation,
    ReservationParticipant,
    ReservationStatus,
    ReservationType,
)
from apps.restaurants.models import Restaurant, Table
from common.exceptions import NoActiveReservationError


def _make_reservation(
    *,
    restaurant: Restaurant,
    table: Table,
    status: str = ReservationStatus.ACTIVE,
    res_type: str = ReservationType.PRE_BOOKED,
    start_offset: timedelta = timedelta(minutes=-30),
    end_offset: timedelta = timedelta(hours=1),
    open_session: bool = False,
) -> Reservation:
    now = timezone.now()
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now + start_offset,
        end_at=now + end_offset,
        status=status,
        type=res_type,
    )
    if open_session:
        Session.objects.create(
            restaurant=restaurant,
            table=table,
            reservation=reservation,
            guest_count=reservation.guest_count,
            status=SessionStatus.OPEN,
            currency="UAH",
            opened_at=reservation.start_at,
            ends_at=reservation.end_at,
        )
    return reservation


@pytest.mark.django_db
def test_returns_cart_for_active_reservation(restaurant: Restaurant, table: Table) -> None:
    _make_reservation(restaurant=restaurant, table=table, open_session=True)

    session = ensure_active_cart_for_table(table=table)

    assert session.status == CartSessionStatus.ACTIVE
    assert CartSession.objects.filter(reservation__table=table).count() == 1


@pytest.mark.django_db
def test_active_reservation_without_open_session_does_not_yield_cart(
    restaurant: Restaurant,
    table: Table,
) -> None:
    _make_reservation(
        restaurant=restaurant,
        table=table,
        start_offset=timedelta(minutes=10),
        end_offset=timedelta(hours=2),
    )

    with pytest.raises(NoActiveReservationError):
        ensure_active_cart_for_table(table=table)


@pytest.mark.django_db
def test_second_call_returns_same_session(restaurant: Restaurant, table: Table) -> None:
    _make_reservation(restaurant=restaurant, table=table, open_session=True)

    first = ensure_active_cart_for_table(table=table)
    second = ensure_active_cart_for_table(table=table)

    assert first.pk == second.pk
    assert CartSession.objects.count() == 1


@pytest.mark.django_db
def test_no_reservation_raises(table: Table) -> None:
    with pytest.raises(NoActiveReservationError) as exc:
        ensure_active_cart_for_table(table=table)

    assert exc.value.default_code == "NO_ACTIVE_RESERVATION"
    assert not CartSession.objects.exists()


@pytest.mark.django_db
def test_expired_reservation_gives_no_cart(restaurant: Restaurant, table: Table) -> None:
    _make_reservation(
        restaurant=restaurant,
        table=table,
        start_offset=timedelta(hours=-3),
        end_offset=timedelta(hours=-1),
    )

    with pytest.raises(NoActiveReservationError):
        ensure_active_cart_for_table(table=table)

    assert not CartSession.objects.exists()


@pytest.mark.django_db
def test_extended_session_keeps_table_available_even_if_booked_end_is_past(
    restaurant: Restaurant,
    table: Table,
) -> None:
    reservation = _make_reservation(
        restaurant=restaurant,
        table=table,
        start_offset=timedelta(hours=-3),
        end_offset=timedelta(minutes=-30),
    )
    Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=reservation.guest_count,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=reservation.start_at,
        ends_at=timezone.now() + timedelta(minutes=15),
    )

    session = ensure_active_cart_for_table(table=table)

    assert session.status == CartSessionStatus.ACTIVE
    assert session.reservation_id == reservation.id


@pytest.mark.django_db
@pytest.mark.parametrize(
    "res_type",
    [ReservationType.PRE_BOOKED, ReservationType.WALK_IN],
)
def test_walk_in_and_pre_booked_handled_the_same(restaurant: Restaurant, table: Table, res_type: str) -> None:
    _make_reservation(restaurant=restaurant, table=table, res_type=res_type, open_session=True)

    session = ensure_active_cart_for_table(table=table)

    assert session.status == CartSessionStatus.ACTIVE
    assert session.reservation.type == res_type


@pytest.mark.django_db
def test_optional_user_becomes_creator_and_participant(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
) -> None:
    user = user_factory(role=RoleCode.CUSTOMER)
    user.save()
    reservation = _make_reservation(restaurant=restaurant, table=table, open_session=True)
    ReservationParticipant.objects.create(reservation=reservation, user=user)

    session = ensure_active_cart_for_table(table=table, user=user)

    assert session.created_by_id == user.id
    assert session.participants.filter(id=user.id).exists()


@pytest.mark.django_db
def test_guest_call_leaves_creator_null(restaurant: Restaurant, table: Table) -> None:
    _make_reservation(restaurant=restaurant, table=table, open_session=True)

    session = ensure_active_cart_for_table(table=table)

    assert session.created_by_id is None


@pytest.mark.django_db(transaction=True)
def test_concurrent_scans_create_exactly_one_session(restaurant: Restaurant, table: Table) -> None:
    _make_reservation(restaurant=restaurant, table=table, open_session=True)
    attempts = 50

    def _attempt() -> int:
        try:
            session = ensure_active_cart_for_table(table=table)
            return session.pk
        finally:
            connection.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(attempts, 25)) as pool:
        futures = [pool.submit(_attempt) for _ in range(attempts)]
        session_pks = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert CartSession.objects.filter(status=CartSessionStatus.ACTIVE).count() == 1
    assert len(set(session_pks)) == 1
    assert len(session_pks) == attempts
