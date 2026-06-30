# mypy: disable-error-code="no-untyped-call"
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.reservations.models import Reservation, ReservationStatus
from apps.reservations.services import reschedule_reservation
from apps.restaurants.models import Restaurant, RestaurantSettings, Table, Zone
from common.exceptions import ReservationConflictError, RestaurantClosedError

pytestmark = pytest.mark.django_db


def _reservation(
    *,
    restaurant: Restaurant,
    table: Table,
    customer: Any = None,
    guest_count: int = 2,
    res_status: str = ReservationStatus.PENDING,
    start_offset_hours: int = 2,
) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        customer=customer,
        guest_count=guest_count,
        start_at=now + timedelta(hours=start_offset_hours),
        end_at=now + timedelta(hours=start_offset_hours + 1),
        status=res_status,
    )


def _url(res: Reservation) -> str:
    return f"/api/reservations/reservations/{res.public_id}/"


class TestRescheduleExtended:
    def test_reschedule_to_different_table(
        self, restaurant: Restaurant, table: Table, zone: Zone, user_factory: Any
    ) -> None:
        from .conftest import Table as TableModel

        table2 = TableModel.objects.create(
            restaurant=restaurant,
            public_number="T2",
            capacity=4,
            zone=zone,
            active=True,
        )
        res = _reservation(restaurant=restaurant, table=table)

        now = timezone.now()
        new_start = now + timedelta(hours=5)
        new_end = new_start + timedelta(hours=1)

        result = reschedule_reservation(
            res,
            {
                "table": table2,
                "start_at": new_start,
                "end_at": new_end,
            },
        )
        result.refresh_from_db()
        assert result.table_id == table2.pk

    def test_reschedule_to_smaller_table_capacity_exceeded(
        self, restaurant: Restaurant, table: Table, zone: Zone, user_factory: Any
    ) -> None:
        from .conftest import Table as TableModel

        small_table = TableModel.objects.create(
            restaurant=restaurant,
            public_number="T-SMALL",
            capacity=2,
            zone=zone,
            active=True,
        )
        res = _reservation(restaurant=restaurant, table=table, guest_count=4)

        now = timezone.now()
        new_start = now + timedelta(hours=5)
        new_end = new_start + timedelta(hours=1)

        with pytest.raises(ReservationConflictError, match="capacity"):
            reschedule_reservation(
                res,
                {
                    "table": small_table,
                    "start_at": new_start,
                    "end_at": new_end,
                },
            )

    def test_reschedule_completed_rejected(
        self, restaurant: Restaurant, table: Table, user_factory: Any
    ) -> None:
        res = _reservation(restaurant=restaurant, table=table, res_status=ReservationStatus.COMPLETED)

        now = timezone.now()
        with pytest.raises(Exception):
            reschedule_reservation(
                res,
                {
                    "start_at": now + timedelta(hours=5),
                    "end_at": now + timedelta(hours=6),
                },
            )

    def test_reschedule_active_allows_prolong(
        self, restaurant: Restaurant, table: Table, user_factory: Any
    ) -> None:
        res = _reservation(restaurant=restaurant, table=table, res_status=ReservationStatus.ACTIVE)

        now = timezone.now()
        new_end = now + timedelta(hours=5)

        result = reschedule_reservation(res, {"end_at": new_end})
        result.refresh_from_db()
        assert result.end_at == new_end

    def test_reschedule_active_rejects_table_change(
        self, restaurant: Restaurant, table: Table, zone: Zone, user_factory: Any
    ) -> None:
        from .conftest import Table as TableModel

        table2 = TableModel.objects.create(
            restaurant=restaurant,
            public_number="T2",
            capacity=4,
            zone=zone,
            active=True,
        )
        res = _reservation(restaurant=restaurant, table=table, res_status=ReservationStatus.ACTIVE)

        with pytest.raises(ReservationConflictError, match="prolonged"):
            reschedule_reservation(res, {"table": table2})

    def test_reschedule_outside_operating_hours_rejected(
        self, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        res = _reservation(restaurant=restaurant, table=table)

        now = timezone.now()
        tomorrow = now + timedelta(days=1)
        new_start = tomorrow.replace(hour=3, minute=0, second=0, microsecond=0)
        new_end = new_start + timedelta(hours=1)

        with pytest.raises(RestaurantClosedError):
            reschedule_reservation(
                res,
                {
                    "start_at": new_start,
                    "end_at": new_end,
                },
            )
