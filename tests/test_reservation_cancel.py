# mypy: disable-error-code="no-untyped-call"
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.reservations.models import Reservation, ReservationStatus
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

        result = cancel_reservation(res, actor=actor)
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

        result = cancel_reservation(res, actor=actor)
        result.refresh_from_db()
        assert result.status == ReservationStatus.CANCELLED

    def test_cannot_cancel_completed_reservation(
        self, api: Any, restaurant: Restaurant, table: Table, user_factory: Any
    ) -> None:
        customer = user_factory()
        customer.save()
        res = _reservation(restaurant=restaurant, table=table, customer=customer, res_status=ReservationStatus.COMPLETED)
        actor = user_factory(role=RoleCode.ADMIN)
        actor.save()

        from apps.reservations.services import cancel_reservation

        with pytest.raises(ReservationCancelError, match="Only pending or active"):
            cancel_reservation(res, actor=actor)

    def test_cannot_cancel_already_cancelled(
        self, api: Any, restaurant: Restaurant, table: Table, user_factory: Any
    ) -> None:
        customer = user_factory()
        customer.save()
        res = _reservation(restaurant=restaurant, table=table, customer=customer, res_status=ReservationStatus.CANCELLED)
        actor = user_factory(role=RoleCode.ADMIN)
        actor.save()

        from apps.reservations.services import cancel_reservation

        with pytest.raises(ReservationCancelError, match="Only pending or active"):
            cancel_reservation(res, actor=actor)


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
