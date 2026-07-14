# mypy: disable-error-code="no-untyped-call"
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.orders.models import CartSessionStatus, Session, SessionStatus
from apps.orders.services import ensure_active_cart_for_table
from apps.reservations.models import Reservation, ReservationStatus
from apps.reservations.services import cancel_reservation
from apps.restaurants.models import Restaurant, Table
from common.exceptions import ReservationCancelError

from .conftest import AuthContext

pytestmark = pytest.mark.django_db


def _reservation(
    *,
    restaurant: Restaurant,
    table: Table,
    customer: Any,
    res_status: str = ReservationStatus.PENDING,
    start_offset_hours: int = 2,
) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        customer=customer,
        guest_count=2,
        start_at=now + timedelta(hours=start_offset_hours),
        end_at=now + timedelta(hours=start_offset_hours + 1),
        status=res_status,
    )


def _url(res: Reservation) -> str:
    return f"/api/reservations/reservations/{res.public_id}/"


class TestCancelReservationService:
    def test_cancel_pending_reservation(
        self, api: Any, restaurant: Restaurant, table: Table, user_factory: Any
    ) -> None:
        customer = user_factory()
        customer.save()
        res = _reservation(restaurant=restaurant, table=table, customer=customer)
        actor = user_factory(role=RoleCode.ADMIN)
        actor.save()

        from apps.reservations.services import cancel_reservation

        result = cancel_reservation(res)
        result.refresh_from_db()
        assert result.status == ReservationStatus.CANCELLED

    def test_cancel_active_reservation(
        self, api: Any, restaurant: Restaurant, table: Table, user_factory: Any
    ) -> None:
        customer = user_factory()
        customer.save()
        res = _reservation(restaurant=restaurant, table=table, customer=customer, res_status=ReservationStatus.ACTIVE)
        actor = user_factory(role=RoleCode.WAITER)
        actor.save()

        from apps.reservations.services import cancel_reservation

        result = cancel_reservation(res)
        result.refresh_from_db()
        assert result.status == ReservationStatus.CANCELLED

    def test_cannot_cancel_completed_reservation(
        self, api: Any, restaurant: Restaurant, table: Table, user_factory: Any
    ) -> None:
        customer = user_factory()
        customer.save()
        res = _reservation(
            restaurant=restaurant, table=table, customer=customer, res_status=ReservationStatus.COMPLETED
        )
        actor = user_factory(role=RoleCode.ADMIN)
        actor.save()

        from apps.reservations.services import cancel_reservation

        with pytest.raises(ReservationCancelError, match="Only pending or active"):
            cancel_reservation(res)

    def test_cannot_cancel_already_cancelled(
        self, api: Any, restaurant: Restaurant, table: Table, user_factory: Any
    ) -> None:
        customer = user_factory()
        customer.save()
        res = _reservation(
            restaurant=restaurant, table=table, customer=customer, res_status=ReservationStatus.CANCELLED
        )
        actor = user_factory(role=RoleCode.ADMIN)
        actor.save()

        from apps.reservations.services import cancel_reservation

        with pytest.raises(ReservationCancelError, match="Only pending or active"):
            cancel_reservation(res)


class TestCancelReservationAPI:
    def test_customer_can_cancel_own_pending(
        self, api: Any, restaurant: Restaurant, table: Table, user_factory: Any
    ) -> None:
        customer = user_factory()
        customer.save()
        res = _reservation(restaurant=restaurant, table=table, customer=customer)
        ctx: AuthContext = api(role=RoleCode.CUSTOMER)
        # Force authenticate as the customer
        ctx.client.force_authenticate(user=customer)

        resp = ctx.client.patch(_url(res), {"status": "cancelled"}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        res.refresh_from_db()
        assert res.status == ReservationStatus.CANCELLED

    def test_customer_cannot_cancel_active(
        self, api: Any, restaurant: Restaurant, table: Table, user_factory: Any
    ) -> None:
        customer = user_factory()
        customer.save()
        res = _reservation(restaurant=restaurant, table=table, customer=customer, res_status=ReservationStatus.ACTIVE)
        ctx: AuthContext = api(role=RoleCode.CUSTOMER)
        ctx.client.force_authenticate(user=customer)

        resp = ctx.client.patch(_url(res), {"status": "cancelled"}, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_staff_can_cancel_active(
        self, api: Any, restaurant: Restaurant, table: Table, user_factory: Any
    ) -> None:
        customer = user_factory()
        customer.save()
        res = _reservation(restaurant=restaurant, table=table, customer=customer, res_status=ReservationStatus.ACTIVE)
        ctx: AuthContext = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)

        resp = ctx.client.patch(_url(res), {"status": "cancelled"}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        res.refresh_from_db()
        assert res.status == ReservationStatus.CANCELLED


@pytest.mark.django_db
def test_cancel_reservation_closes_its_open_session(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
) -> None:
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
        ends_at=reservation.end_at,
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
        ends_at=reservation.end_at,
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


@pytest.mark.django_db
def test_cancel_active_reservation_closes_its_active_cart(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
) -> None:
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
    Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=2,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=reservation.start_at,
        ends_at=reservation.end_at,
    )
    cart = ensure_active_cart_for_table(table=table)

    cancel_reservation(reservation=reservation)

    cart.refresh_from_db()
    assert cart.status == CartSessionStatus.CLOSED
