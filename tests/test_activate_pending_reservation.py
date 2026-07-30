# mypy: disable-error-code="no-untyped-call"
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.authentication.models import RoleCode
from apps.menu.models import MenuItem
from apps.orders.models import Order, OrderItem, OrderItemStatus, Session, SessionStatus
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
        res.status = ReservationStatus.COMPLETED
        res.save()

        with pytest.raises(ReservationConflictError, match="Only pending"):
            activate_pending_reservation(res, actor=actor)

    def test_idempotent_for_active(
        self, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings, user_factory: Any
    ) -> None:
        actor = user_factory(role=RoleCode.WAITER)
        actor.save()
        res = _reservation(restaurant=restaurant, table=table)
        res.status = ReservationStatus.ACTIVE
        res.save()

        result = activate_pending_reservation(res, actor=actor)
        assert result.status == ReservationStatus.ACTIVE

    def test_rejects_if_open_session_exists(
        self, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings, user_factory: Any
    ) -> None:
        actor = user_factory(role=RoleCode.WAITER)
        actor.save()
        res = _reservation(restaurant=restaurant, table=table)

        # Create an existing open session (needs a reservation)
        other_res = _reservation(restaurant=restaurant, table=table, start_offset_hours=5)
        other_res.status = ReservationStatus.ACTIVE
        other_res.save(update_fields=["status"])
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

    def test_rejects_if_prolonged_open_session_exists(
        self, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings, user_factory: Any
    ) -> None:
        actor = user_factory(role=RoleCode.WAITER)
        actor.save()
        now = timezone.now()
        res = _reservation(restaurant=restaurant, table=table)

        other_res = Reservation.objects.create(
            restaurant=restaurant,
            table=table,
            guest_count=2,
            start_at=now - timedelta(hours=1),
            end_at=now - timedelta(minutes=5),
            status=ReservationStatus.ACTIVE,
        )
        session = Session.objects.create(
            restaurant=restaurant,
            table=table,
            reservation=other_res,
            opened_by=actor,
            guest_count=2,
            currency="UAH",
            status=SessionStatus.OPEN,
            opened_at=timezone.now() - timedelta(hours=1),
            ends_at=now + timedelta(minutes=30),
        )
        original_ends_at = session.ends_at

        with pytest.raises(ReservationConflictError, match="active session"):
            activate_pending_reservation(res, actor=actor)

        session.refresh_from_db()
        assert session.status == SessionStatus.OPEN
        assert session.ends_at == original_ends_at

    def test_force_closes_stale_session_with_unserved_items(
        self,
        restaurant: Restaurant,
        table: Table,
        restaurant_settings: RestaurantSettings,
        user_factory: Any,
        item: MenuItem,
    ) -> None:
        # A previous, unrelated reservation's session can still have unserved
        # items (nobody clicked "served") by the time it goes stale. Seating a
        # brand-new party must not be blocked by that old, unrelated mess —
        # see bug where activate_pending_reservation raised UnservedItemsError
        # from a stale session instead of just clearing it out of the way.
        actor = user_factory(role=RoleCode.WAITER)
        actor.save()
        now = timezone.now()
        res = _reservation(restaurant=restaurant, table=table)

        stale_res = Reservation.objects.create(
            restaurant=restaurant,
            table=table,
            guest_count=2,
            start_at=now - timedelta(hours=3),
            end_at=now - timedelta(hours=1),
            status=ReservationStatus.ACTIVE,
        )
        stale_session = Session.objects.create(
            restaurant=restaurant,
            table=table,
            reservation=stale_res,
            guest_count=2,
            currency="UAH",
            status=SessionStatus.OPEN,
            opened_at=now - timedelta(hours=3),
            ends_at=stale_res.end_at,
        )
        order = Order.objects.create(restaurant=restaurant, session=stale_session, currency="UAH")
        OrderItem.objects.create(
            restaurant=restaurant,
            order=order,
            menu_item=item,
            guest_slot=1,
            quantity=1,
            status=OrderItemStatus.READY,
            unit_price=item.price,
            total_price=item.price,
        )

        result = activate_pending_reservation(res, actor=actor)

        result.refresh_from_db()
        stale_session.refresh_from_db()
        assert result.status == ReservationStatus.ACTIVE
        assert stale_session.status == SessionStatus.CLOSED

    def test_promotes_scheduled_session_from_paid_preorder(
        self, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings, user_factory: Any
    ) -> None:
        # confirm_and_pay_preorder leaves this reservation a SCHEDULED Session
        # while it's still PENDING (the bill exists, the table isn't occupied).
        # Seating it must promote that same Session to OPEN and stamp the real
        # seating time — not raw-create a second one (reservation OneToOne /
        # one-open-session-per-table constraint), which is the bug where
        # "Посадити" raised a bare IntegrityError instead of activating.
        actor = user_factory(role=RoleCode.WAITER)
        actor.save()
        res = _reservation(restaurant=restaurant, table=table, start_offset_hours=3)
        scheduled_at = res.start_at
        preorder_session = Session.objects.create(
            restaurant=restaurant,
            table=table,
            reservation=res,
            guest_count=2,
            currency="UAH",
            status=SessionStatus.SCHEDULED,
            opened_at=scheduled_at,
            ends_at=res.end_at,
        )

        result = activate_pending_reservation(res, actor=actor)

        result.refresh_from_db()
        assert result.status == ReservationStatus.ACTIVE
        assert Session.objects.filter(reservation=result).count() == 1
        session = Session.objects.get(reservation=result)
        assert session.pk == preorder_session.pk
        assert session.status == SessionStatus.OPEN
        assert session.opened_at != scheduled_at
        assert timezone.now() - session.opened_at < timedelta(minutes=1)
        assert session.opened_by == actor

    def test_rejects_if_earlier_pending_exists(
        self, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings, user_factory: Any
    ) -> None:
        actor = user_factory(role=RoleCode.WAITER)
        actor.save()
        now = timezone.now()

        # Earlier pending reservation (already started)
        Reservation.objects.create(
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
