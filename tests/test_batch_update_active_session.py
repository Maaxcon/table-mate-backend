# mypy: disable-error-code="no-untyped-call"
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.orders.models import Session, SessionStatus
from apps.reservations.models import Reservation, ReservationStatus
from apps.reservations.services import activate_pending_reservation
from apps.restaurants.models import Restaurant, RestaurantSettings, Table

from .conftest import AuthContext

pytestmark = pytest.mark.django_db


def _reservation(
    *,
    restaurant: Restaurant,
    table: Table,
    start_offset_hours: int = 2,
    duration_hours: int = 1,
    res_status: str = ReservationStatus.PENDING,
) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now + timedelta(hours=start_offset_hours),
        end_at=now + timedelta(hours=start_offset_hours + duration_hours),
        status=res_status,
    )


def _url() -> str:
    return "/api/reservations/reservations/batch-update/"


class TestBatchUpdateActiveMovesSession:
    def test_active_move_changes_session_table_not_reservation_table(
        self,
        api: Any,
        restaurant: Restaurant,
        table: Table,
        zone: Any,
        restaurant_settings: RestaurantSettings,
        user_factory: Any,
    ) -> None:
        """Dragging an active reservation to another table moves the session, not the booking."""
        from .conftest import Table as TableModel

        table2 = TableModel.objects.create(
            restaurant=restaurant,
            public_number="T2",
            capacity=4,
            zone=zone,
            active=True,
        )

        # Create and activate a reservation on table1
        actor = user_factory(role=RoleCode.WAITER)
        actor.save()
        res = _reservation(restaurant=restaurant, table=table, res_status=ReservationStatus.PENDING)
        activated = activate_pending_reservation(res, actor=actor)

        original_reservation_table_id = activated.table_id
        session = Session.objects.get(reservation=activated, status=SessionStatus.OPEN)
        assert session.table_id == table.pk

        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)

        tomorrow = (timezone.now() + timedelta(days=1)).date()
        resp = ctx.client.post(
            _url(),
            {
                "changes": [
                    {
                        "reservation_id": str(activated.public_id),
                        "new_table_id": str(table2.public_id),
                        "new_date": tomorrow.isoformat(),
                        "new_start_time": "12:00",
                        "new_end_time": "14:00",
                    }
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK

        # Reservation booking is untouched
        activated.refresh_from_db()
        assert activated.table_id == original_reservation_table_id, "Reservation table must not change for active"
        assert activated.status == ReservationStatus.ACTIVE

        # Session moved to table2
        session.refresh_from_db()
        assert session.table_id == table2.pk, "Session table must move to the new table"

    def test_active_prolong_changes_session_ends_at_not_reservation_end_at(
        self,
        api: Any,
        restaurant: Restaurant,
        table: Table,
        zone: Any,
        restaurant_settings: RestaurantSettings,
        user_factory: Any,
    ) -> None:
        """Extending an active reservation's end time updates session.ends_at, not reservation.end_at."""
        actor = user_factory(role=RoleCode.WAITER)
        actor.save()
        res = _reservation(restaurant=restaurant, table=table, res_status=ReservationStatus.PENDING)
        activated = activate_pending_reservation(res, actor=actor)

        original_reservation_end = activated.end_at
        session = Session.objects.get(reservation=activated, status=SessionStatus.OPEN)
        original_session_end = session.ends_at

        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)

        tomorrow = (timezone.now() + timedelta(days=1)).date()
        resp = ctx.client.post(
            _url(),
            {
                "changes": [
                    {
                        "reservation_id": str(activated.public_id),
                        "new_table_id": str(table.public_id),
                        "new_date": tomorrow.isoformat(),
                        "new_start_time": "12:00",
                        "new_end_time": "16:00",
                    }
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK

        # Reservation end_at is untouched
        activated.refresh_from_db()
        assert activated.end_at == original_reservation_end, "Reservation end_at must not change for active"

        # Session ends_at is updated
        session.refresh_from_db()
        assert session.ends_at != original_session_end, "Session ends_at must be updated"

    def test_pending_move_changes_reservation_table(
        self, api: Any, restaurant: Restaurant, table: Table, zone: Any, restaurant_settings: RestaurantSettings
    ) -> None:
        """Moving a PENDING reservation still changes the reservation's table (not session)."""
        from .conftest import Table as TableModel

        table2 = TableModel.objects.create(
            restaurant=restaurant,
            public_number="T2",
            capacity=4,
            zone=zone,
            active=True,
        )
        res = _reservation(restaurant=restaurant, table=table, res_status=ReservationStatus.PENDING)

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
        assert res.table_id == table2.pk, "Pending reservation table must change"
