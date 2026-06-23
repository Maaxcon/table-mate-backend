from typing import Any

import pytest
from django.utils import timezone

from apps.authentication.models import RoleCode
from apps.orders.models import OrderItem, OrderItemStatus, SessionStatus
from apps.orders.services import create_order_with_items, open_session
from apps.reservations.models import ReservationStatus
from apps.reservations.services import move_session_to_table
from apps.restaurants.models import Table


@pytest.mark.django_db
class TestMoveSessionToTable:
    def test_success(
        self,
        api: Any,
        restaurant: Any,
        table: Any,
        item: Any,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)

        table2 = Table.objects.create(
            restaurant=restaurant,
            table_number="T2",
            capacity=4,
            active=True,
        )

        session = open_session(
            restaurant_id=restaurant.id,
            table=table,
            guest_count=2,
            opened_by=auth.user,
            currency="UAH",
            opened_at=timezone.now(),
            actor=auth.user,
        )

        create_order_with_items(
            session=session,
            items=[{"menu_item": item, "guest_slot": 1, "quantity": 2}],
            actor=auth.user,
        )

        old_reservation = session.reservation

        moved = move_session_to_table(
            session,
            new_table_id=str(table2.public_id),
            actor=auth.user,
        )

        moved.refresh_from_db()
        assert moved.table is not None
        assert moved.table_id == table2.pk

        old_reservation.refresh_from_db()
        assert old_reservation.status == ReservationStatus.CANCELLED

        new_reservation = moved.reservation
        assert new_reservation.status == ReservationStatus.ACTIVE
        assert new_reservation.table_id == table2.pk
        assert new_reservation.pk != old_reservation.pk

        items = list(OrderItem.objects.filter(order__session=moved))
        assert len(items) == 1
        assert items[0].status == OrderItemStatus.PENDING

    def test_rejects_non_open_session(
        self,
        api: Any,
        restaurant: Any,
        table: Any,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)

        session = open_session(
            restaurant_id=restaurant.id,
            table=table,
            guest_count=2,
            opened_by=auth.user,
            currency="UAH",
            opened_at=timezone.now(),
            actor=auth.user,
        )

        session.status = SessionStatus.CLOSED
        session.save(update_fields=["status"])

        table2 = Table.objects.create(
            restaurant=restaurant,
            table_number="T2",
            capacity=4,
            active=True,
        )

        from common.exceptions import ReservationConflictError

        with pytest.raises(ReservationConflictError, match="Can only move an open session"):
            move_session_to_table(
                session,
                new_table_id=str(table2.public_id),
                actor=auth.user,
            )

    def test_rejects_inactive_target_table(
        self,
        api: Any,
        restaurant: Any,
        table: Any,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)

        session = open_session(
            restaurant_id=restaurant.id,
            table=table,
            guest_count=2,
            opened_by=auth.user,
            currency="UAH",
            opened_at=timezone.now(),
            actor=auth.user,
        )

        inactive_table = Table.objects.create(
            restaurant=restaurant,
            table_number="T2",
            capacity=4,
            active=False,
        )

        from rest_framework.exceptions import NotFound

        with pytest.raises(NotFound, match="Target table not found or inactive"):
            move_session_to_table(
                session,
                new_table_id=str(inactive_table.public_id),
                actor=auth.user,
            )

    def test_rejects_same_table(
        self,
        api: Any,
        restaurant: Any,
        table: Any,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)

        session = open_session(
            restaurant_id=restaurant.id,
            table=table,
            guest_count=2,
            opened_by=auth.user,
            currency="UAH",
            opened_at=timezone.now(),
            actor=auth.user,
        )

        from common.exceptions import ReservationConflictError

        with pytest.raises(ReservationConflictError, match="Session is already at this table"):
            move_session_to_table(
                session,
                new_table_id=str(table.public_id),
                actor=auth.user,
            )
