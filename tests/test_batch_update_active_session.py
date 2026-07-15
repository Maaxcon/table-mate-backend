# mypy: disable-error-code="no-untyped-call"
from datetime import datetime, time, timedelta
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

    def test_active_prolong_uses_opened_at_time_for_midnight_rollover(
        self,
        api: Any,
        restaurant: Restaurant,
        table: Table,
        zone: Any,
        restaurant_settings: RestaurantSettings,
        user_factory: Any,
    ) -> None:
        """Active rows must decide midnight rollover from the seated time, not the client's booked start."""
        actor = user_factory(role=RoleCode.WAITER)
        actor.save()

        booked_date = (timezone.now() - timedelta(days=1)).date()
        opened_at = timezone.make_aware(datetime.combine(booked_date + timedelta(days=1), time(0, 10)))
        reservation = Reservation.objects.create(
            restaurant=restaurant,
            table=table,
            guest_count=2,
            start_at=timezone.make_aware(datetime.combine(booked_date, time(23, 0))),
            end_at=opened_at + timedelta(hours=1),
            status=ReservationStatus.ACTIVE,
        )
        session = Session.objects.create(
            restaurant=restaurant,
            table=table,
            reservation=reservation,
            guest_count=2,
            status=SessionStatus.OPEN,
            currency="UAH",
            opened_at=opened_at,
            ends_at=opened_at + timedelta(hours=1),
        )

        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)

        resp = ctx.client.post(
            _url(),
            {
                "changes": [
                    {
                        "reservation_id": str(reservation.public_id),
                        "new_table_id": str(table.public_id),
                        "new_date": opened_at.date().isoformat(),
                        "new_start_time": "23:00",
                        "new_end_time": "00:20",
                    }
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK

        session.refresh_from_db()
        assert session.ends_at.date() == opened_at.date()
        assert session.ends_at.time().replace(second=0, microsecond=0) == time(0, 20)

    def test_batch_cannot_double_book_two_active_sessions_onto_one_table(
        self,
        api: Any,
        restaurant: Restaurant,
        table: Table,
        zone: Any,
        restaurant_settings: RestaurantSettings,
        user_factory: Any,
    ) -> None:
        """Two seated parties cannot be batch-moved onto the same physical table.

        Regression for the double-booking hole: active moves mutate the OPEN Session
        (which has no reservation-level overlap constraint), so the intra-batch guard
        must catch two overlapping sessions targeting one table.
        """
        from .conftest import Table as TableModel

        table2 = TableModel.objects.create(
            restaurant=restaurant, public_number="T2", capacity=4, zone=zone, active=True
        )

        actor = user_factory(role=RoleCode.WAITER)
        actor.save()
        res1 = _reservation(restaurant=restaurant, table=table, res_status=ReservationStatus.PENDING)
        res2 = _reservation(restaurant=restaurant, table=table2, res_status=ReservationStatus.PENDING)
        activated1 = activate_pending_reservation(res1, actor=actor)
        activated2 = activate_pending_reservation(res2, actor=actor)

        ctx: AuthContext = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        tomorrow = (timezone.now() + timedelta(days=1)).date()
        resp = ctx.client.post(
            _url(),
            {
                "changes": [
                    # Both seated parties targeting table1 with overlapping windows.
                    {
                        "reservation_id": str(activated1.public_id),
                        "new_table_id": str(table.public_id),
                        "new_date": tomorrow.isoformat(),
                        "new_start_time": "18:00",
                        "new_end_time": "20:00",
                    },
                    {
                        "reservation_id": str(activated2.public_id),
                        "new_table_id": str(table.public_id),
                        "new_date": tomorrow.isoformat(),
                        "new_start_time": "18:15",
                        "new_end_time": "20:00",
                    },
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_409_CONFLICT

        # No physical table may end up with two open sessions.
        assert Session.objects.filter(table=table, status=SessionStatus.OPEN).count() == 1
        # The second session was rolled back to its original table.
        session2 = Session.objects.get(reservation=activated2, status=SessionStatus.OPEN)
        assert session2.table_id == table2.pk

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
