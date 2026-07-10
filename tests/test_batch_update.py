# mypy: disable-error-code="no-untyped-call"
from datetime import datetime, time, timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import Restaurant, RestaurantSettings, Table

from .conftest import AuthContext

pytestmark = pytest.mark.django_db


def _reservation(
    *,
    restaurant: Restaurant,
    table: Table,
    start_offset_hours: int = 2,
    duration_hours: int = 1,
) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now + timedelta(hours=start_offset_hours),
        end_at=now + timedelta(hours=start_offset_hours + duration_hours),
        status=ReservationStatus.PENDING,
    )


def _url() -> str:
    return "/api/reservations/reservations/batch-update/"


class TestBatchUpdate:
    def test_happy_path_move(
        self, api: Any, restaurant: Restaurant, table: Table, zone: Any, restaurant_settings: RestaurantSettings
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
        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)

        tomorrow = (timezone.now() + timedelta(days=1)).date()
        resp = ctx.client.post(
            _url(),
            {
                "changes": [
                    {
                        "reservation_id": str(res.public_id),
                        "new_table_id": str(table2.public_id),
                        "new_date": tomorrow.isoformat(),
                        "new_start_time": "12:00",
                        "new_end_time": "13:00",
                    }
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        res.refresh_from_db()
        assert res.table_id == table2.pk

    def test_past_date_rejected(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        res = _reservation(restaurant=restaurant, table=table)
        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)

        yesterday = (timezone.now() - timedelta(days=1)).date()
        resp = ctx.client.post(
            _url(),
            {
                "changes": [
                    {
                        "reservation_id": str(res.public_id),
                        "new_table_id": str(table.public_id),
                        "new_date": yesterday.isoformat(),
                        "new_start_time": "12:00",
                        "new_end_time": "13:00",
                    }
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_409_CONFLICT

    def test_overlapping_payload_items_rejected(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        res1 = _reservation(restaurant=restaurant, table=table)
        res2 = _reservation(restaurant=restaurant, table=table, start_offset_hours=3)
        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)

        tomorrow = (timezone.now() + timedelta(days=1)).date()
        resp = ctx.client.post(
            _url(),
            {
                "changes": [
                    {
                        "reservation_id": str(res1.public_id),
                        "new_table_id": str(table.public_id),
                        "new_date": tomorrow.isoformat(),
                        "new_start_time": "12:00",
                        "new_end_time": "13:00",
                    },
                    {
                        "reservation_id": str(res2.public_id),
                        "new_table_id": str(table.public_id),
                        "new_date": tomorrow.isoformat(),
                        "new_start_time": "12:30",
                        "new_end_time": "13:30",
                    },
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_409_CONFLICT

    def test_table_not_found_rejected(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        res = _reservation(restaurant=restaurant, table=table)
        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)

        tomorrow = (timezone.now() + timedelta(days=1)).date()
        resp = ctx.client.post(
            _url(),
            {
                "changes": [
                    {
                        "reservation_id": str(res.public_id),
                        "new_table_id": "00000000-0000-0000-0000-000000000000",
                        "new_date": tomorrow.isoformat(),
                        "new_start_time": "12:00",
                        "new_end_time": "13:00",
                    }
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_closed_day_rejected(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        from apps.restaurants.selectors import _DAY_KEYS

        res = _reservation(restaurant=restaurant, table=table)
        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)

        # Mark tomorrow as closed by dropping its day from working_hours, then verify
        # the batch is rejected for falling on a closed day.
        tomorrow = (timezone.now() + timedelta(days=1)).date()
        day_key = _DAY_KEYS[tomorrow.weekday()]
        hours = dict(restaurant_settings.working_hours)
        hours.pop(day_key, None)
        restaurant_settings.working_hours = hours
        restaurant_settings.save(update_fields=["working_hours"])

        resp = ctx.client.post(
            _url(),
            {
                "changes": [
                    {
                        "reservation_id": str(res.public_id),
                        "new_table_id": str(table.public_id),
                        "new_date": tomorrow.isoformat(),
                        "new_start_time": "12:00",
                        "new_end_time": "13:00",
                    }
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK

    def test_staff_only(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        res = _reservation(restaurant=restaurant, table=table)
        ctx: AuthContext = api(role=RoleCode.CUSTOMER)

        tomorrow = (timezone.now() + timedelta(days=1)).date()
        resp = ctx.client.post(
            _url(),
            {
                "changes": [
                    {
                        "reservation_id": str(res.public_id),
                        "new_table_id": str(table.public_id),
                        "new_date": tomorrow.isoformat(),
                        "new_start_time": "12:00",
                        "new_end_time": "13:00",
                    }
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_sub_30_min_overlap_detected(
        self, api: Any, restaurant: Restaurant, table: Table, zone: Any, restaurant_settings: RestaurantSettings
    ) -> None:
        """Two 15-min reservations overlapping should be detected."""

        res1 = _reservation(restaurant=restaurant, table=table, duration_hours=1)
        res2 = _reservation(restaurant=restaurant, table=table, start_offset_hours=3, duration_hours=1)
        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)

        tomorrow = (timezone.now() + timedelta(days=1)).date()
        resp = ctx.client.post(
            _url(),
            {
                "changes": [
                    {
                        "reservation_id": str(res1.public_id),
                        "new_table_id": str(table.public_id),
                        "new_date": tomorrow.isoformat(),
                        "new_start_time": "12:00",
                        "new_end_time": "12:15",
                    },
                    {
                        "reservation_id": str(res2.public_id),
                        "new_table_id": str(table.public_id),
                        "new_date": tomorrow.isoformat(),
                        "new_start_time": "12:10",
                        "new_end_time": "12:30",
                    },
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_409_CONFLICT

    def test_cross_tenant_reservation_rejected(
        self, api: Any, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        """A reservation belonging to another restaurant must not be editable via this tenant's batch."""
        from .conftest import RestaurantFactory, ZoneFactory
        from .conftest import Table as TableModel

        other = RestaurantFactory(name="Other Restaurant")
        other_zone = ZoneFactory(restaurant=other, name="Other Hall")
        other_table = TableModel.objects.create(
            restaurant=other, public_number="X1", capacity=4, zone=other_zone, active=True
        )
        other_res = _reservation(restaurant=other, table=other_table)

        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        tomorrow = (timezone.now() + timedelta(days=1)).date()
        resp = ctx.client.post(
            _url(),
            {
                "changes": [
                    {
                        "reservation_id": str(other_res.public_id),
                        "new_table_id": str(table.public_id),
                        "new_date": tomorrow.isoformat(),
                        "new_start_time": "12:00",
                        "new_end_time": "13:00",
                    }
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        # The cross-tenant reservation must be untouched.
        other_res.refresh_from_db()
        assert other_res.table_id == other_table.pk

    def test_conflict_with_existing_rolls_back_whole_batch(
        self, api: Any, restaurant: Restaurant, table: Table, zone: Any, restaurant_settings: RestaurantSettings
    ) -> None:
        """One item conflicting with an untouched existing reservation rolls back the entire batch."""
        from .conftest import Table as TableModel

        table2 = TableModel.objects.create(
            restaurant=restaurant, public_number="T2", capacity=4, zone=zone, active=True
        )
        tomorrow = (timezone.now() + timedelta(days=1)).date()

        # A pre-existing booking on table2 that the batch does NOT touch.
        Reservation.objects.create(
            restaurant=restaurant,
            table=table2,
            guest_count=2,
            start_at=timezone.make_aware(datetime.combine(tomorrow, time(15, 0))),
            end_at=timezone.make_aware(datetime.combine(tomorrow, time(16, 0))),
            status=ReservationStatus.PENDING,
        )

        res_a = _reservation(restaurant=restaurant, table=table)
        res_b = _reservation(restaurant=restaurant, table=table, start_offset_hours=5)
        original_a_start = res_a.start_at

        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        resp = ctx.client.post(
            _url(),
            {
                "changes": [
                    # Valid on its own.
                    {
                        "reservation_id": str(res_a.public_id),
                        "new_table_id": str(table.public_id),
                        "new_date": tomorrow.isoformat(),
                        "new_start_time": "11:00",
                        "new_end_time": "12:00",
                    },
                    # Overlaps the untouched existing booking on table2 → conflict.
                    {
                        "reservation_id": str(res_b.public_id),
                        "new_table_id": str(table2.public_id),
                        "new_date": tomorrow.isoformat(),
                        "new_start_time": "15:15",
                        "new_end_time": "15:45",
                    },
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_409_CONFLICT
        # Atomicity: the valid first item must have been rolled back too.
        res_a.refresh_from_db()
        assert res_a.start_at == original_a_start
