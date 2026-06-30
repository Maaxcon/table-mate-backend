# mypy: disable-error-code="no-untyped-call"
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.authentication.models import RoleCode
from apps.orders.models import Session, SessionStatus
from apps.reservations.models import Reservation, ReservationStatus
from apps.reservations.services import activate_pending_reservation
from apps.restaurants.models import Restaurant, RestaurantSettings, Table
from common.exceptions import ReservationConflictError

pytestmark = pytest.mark.django_db


def _reservation(
    *,
    restaurant: Restaurant,
    table: Table,
    customer: Any = None,
    start_offset_hours: int = 0,
) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        customer=customer,
        guest_count=2,
        start_at=now + timedelta(hours=start_offset_hours),
        end_at=now + timedelta(hours=start_offset_hours + 1),
        status=ReservationStatus.PENDING,
    )


class TestActivatePendingReservation:
    def test_happy_path(
        self, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings, user_factory: Any
    ) -> None:
        actor = user_factory(role=RoleCode.WAITER)
        actor.save()
        res = _reservation(restaurant=restaurant, table=table)

        result = activate_pending_reservation(res, actor=actor)
        result.refresh_from_db()
        assert result.status == ReservationStatus.ACTIVE
        assert Session.objects.filter(reservation=result, status=SessionStatus.OPEN).exists()

    def test_rejects_non_pending(
        self, restaurant: Restaurant, table: Table, user_factory: Any
    ) -> None:
        actor = user_factory(role=RoleCode.WAITER)
        actor.save()
        res = _reservation(restaurant=restaurant, table=table)
        res.status = ReservationStatus.ACTIVE
        res.save()

        with pytest.raises(ReservationConflictError, match="Only pending"):
            activate_pending_reservation(res, actor=actor)

    def test_rejects_if_open_session_exists(
        self, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings, user_factory: Any
    ) -> None:
        actor = user_factory(role=RoleCode.WAITER)
        actor.save()
        res = _reservation(restaurant=restaurant, table=table)

        # Create an existing open session (needs a reservation)
        other_res = _reservation(restaurant=restaurant, table=table, start_offset_hours=5)
        Session.objects.create(
            restaurant=restaurant,
            table=table,
            reservation=other_res,
            opened_by=actor,
            guest_count=2,
            currency="UAH",
            status=SessionStatus.OPEN,
            opened_at=timezone.now(),
        )

        with pytest.raises(ReservationConflictError, match="active session"):
            activate_pending_reservation(res, actor=actor)

    def test_rejects_if_earlier_pending_exists(
        self, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings, user_factory: Any
    ) -> None:
        actor = user_factory(role=RoleCode.WAITER)
        actor.save()
        now = timezone.now()

        # Earlier pending reservation (already started)
        earlier = Reservation.objects.create(
            restaurant=restaurant,
            table=table,
            guest_count=2,
            start_at=now - timedelta(minutes=30),
            end_at=now + timedelta(minutes=30),
            status=ReservationStatus.PENDING,
        )

        # Later pending reservation
        later = Reservation.objects.create(
            restaurant=restaurant,
            table=table,
            guest_count=2,
            start_at=now + timedelta(hours=1),
            end_at=now + timedelta(hours=2),
            status=ReservationStatus.PENDING,
        )

        with pytest.raises(ReservationConflictError, match="earlier pending"):
            activate_pending_reservation(later, actor=actor)
