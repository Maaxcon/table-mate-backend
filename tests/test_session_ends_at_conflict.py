# mypy: disable-error-code="no-untyped-call"
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.authentication.models import RoleCode
from apps.orders.models import Session, SessionStatus
from apps.reservations.models import Reservation, ReservationStatus
from apps.reservations.services import _check_reservation_conflict, activate_pending_reservation
from apps.restaurants.models import Restaurant, RestaurantSettings, Table
from common.exceptions import ReservationConflictError

pytestmark = pytest.mark.django_db


def _reservation(
    *,
    restaurant: Restaurant,
    table: Table,
    start_offset_hours: int = 0,
    duration_hours: int = 2,
    status: str = ReservationStatus.PENDING,
) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now + timedelta(hours=start_offset_hours),
        end_at=now + timedelta(hours=start_offset_hours + duration_hours),
        status=status,
    )


class TestConflictUsesSessionActuals:
    def test_active_occupancy_uses_session_opened_at_not_booked_start(
        self, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings, user_factory: Any
    ) -> None:
        """An active reservation blocks from session.opened_at, not the booked start_at."""
        actor = user_factory(role=RoleCode.WAITER)
        actor.save()

        # Booked 20:00-22:00 but seated at now (effectively 19:30-ish)
        res = _reservation(restaurant=restaurant, table=table, start_offset_hours=1, duration_hours=2)
        activated = activate_pending_reservation(res, actor=actor)
        activated.refresh_from_db()

        session = Session.objects.get(reservation=activated, status=SessionStatus.OPEN)
        # Session opened_at should be close to now, booked start_at is now+1h
        assert session.opened_at < activated.start_at

        # A new reservation overlapping the SESSION window (but not the booked window)
        # should be rejected. Booked start is now+1h, so now+30min doesn't overlap booked,
        # but it DOES overlap the session [opened_at, ends_at].
        now = timezone.now()
        with pytest.raises(ReservationConflictError, match="not available"):
            _check_reservation_conflict(
                restaurant_id=restaurant.id,
                table=table,
                start_at=now + timedelta(minutes=30),
                end_at=now + timedelta(hours=1, minutes=30),
            )

    def test_active_occupancy_uses_session_ends_at_not_booked_end(
        self, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings, user_factory: Any
    ) -> None:
        """An active reservation's occupied window ends at session.ends_at, not booked end_at."""
        actor = user_factory(role=RoleCode.WAITER)
        actor.save()

        # Booked now+1h to now+3h. Activate → session.ends_at = booked end_at = now+3h.
        res = _reservation(restaurant=restaurant, table=table, start_offset_hours=1, duration_hours=2)
        activated = activate_pending_reservation(res, actor=actor)
        session = Session.objects.get(reservation=activated, status=SessionStatus.OPEN)

        # Prolong the session to now+4h
        session.ends_at = timezone.now() + timedelta(hours=4)
        session.save(update_fields=["ends_at"])

        # A booking at now+3h15m overlaps the prolonged session but NOT the booked end_at.
        now = timezone.now()
        with pytest.raises(ReservationConflictError, match="not available"):
            _check_reservation_conflict(
                restaurant_id=restaurant.id,
                table=table,
                start_at=now + timedelta(hours=3, minutes=15),
                end_at=now + timedelta(hours=4, minutes=30),
            )

        # A booking at now+4h15m should be fine (after prolonged end)
        _check_reservation_conflict(
            restaurant_id=restaurant.id,
            table=table,
            start_at=now + timedelta(hours=4, minutes=15),
            end_at=now + timedelta(hours=5),
        )

    def test_pending_uses_booked_window(
        self, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings
    ) -> None:
        """A pending reservation still uses the booked [start_at, end_at] for conflict checks."""
        now = timezone.now()
        Reservation.objects.create(
            restaurant=restaurant,
            table=table,
            guest_count=2,
            start_at=now + timedelta(hours=2),
            end_at=now + timedelta(hours=4),
            status=ReservationStatus.PENDING,
        )

        # Overlapping with booked window → conflict
        with pytest.raises(ReservationConflictError, match="not available"):
            _check_reservation_conflict(
                restaurant_id=restaurant.id,
                table=table,
                start_at=now + timedelta(hours=3),
                end_at=now + timedelta(hours=5),
                current_reservation_id=None,
            )

        # Before booked window → no conflict
        _check_reservation_conflict(
            restaurant_id=restaurant.id,
            table=table,
            start_at=now + timedelta(hours=1),
            end_at=now + timedelta(hours=1, minutes=45),
        )

    def test_active_preserves_start_at_on_activation(
        self, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings, user_factory: Any
    ) -> None:
        """Activating a reservation must NOT overwrite start_at (the booking stays pristine)."""
        actor = user_factory(role=RoleCode.WAITER)
        actor.save()

        now = timezone.now()
        booked_start = now + timedelta(hours=1)
        booked_end = now + timedelta(hours=3)
        res = Reservation.objects.create(
            restaurant=restaurant,
            table=table,
            guest_count=2,
            start_at=booked_start,
            end_at=booked_end,
            status=ReservationStatus.PENDING,
        )

        original_start = res.start_at
        activated = activate_pending_reservation(res, actor=actor)
        activated.refresh_from_db()

        assert activated.start_at == original_start, "start_at must not change on activation"
        session = Session.objects.get(reservation=activated, status=SessionStatus.OPEN)
        assert session.opened_at != original_start, "session.opened_at should be the activation time"
        assert session.ends_at == booked_end, "session.ends_at should be the booked end_at"


class TestOrderingRule:
    def test_pending_before_seated_party_rejected(
        self, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings, user_factory: Any
    ) -> None:
        """A pending reservation starting before the seated party's opened_at must be rejected."""
        actor = user_factory(role=RoleCode.WAITER)
        actor.save()

        now = timezone.now()
        # Active session opened at 19:30 (now - 30min), ends at 21:30 (now + 1.5h)
        active = Reservation.objects.create(
            restaurant=restaurant,
            table=table,
            guest_count=2,
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=2),
            status=ReservationStatus.ACTIVE,
        )
        Session.objects.create(
            restaurant=restaurant,
            table=table,
            reservation=active,
            guest_count=2,
            currency="UAH",
            opened_at=now - timedelta(minutes=30),
            ends_at=now + timedelta(hours=1, minutes=30),
            status=SessionStatus.OPEN,
        )

        # Pending booking at 17:00-18:00 — entirely BEFORE the seated party, no overlap
        with pytest.raises(ReservationConflictError, match="must start after the seated party"):
            _check_reservation_conflict(
                restaurant_id=restaurant.id,
                table=table,
                start_at=now - timedelta(hours=2, minutes=30),
                end_at=now - timedelta(hours=1, minutes=30),
            )

    def test_pending_after_seated_party_allowed(
        self, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings, user_factory: Any
    ) -> None:
        """A pending reservation starting after the seated party's window must be allowed."""
        now = timezone.now()
        # Active session opened at 19:30 (now - 30min), ends at 21:00 (now + 1h)
        active = Reservation.objects.create(
            restaurant=restaurant,
            table=table,
            guest_count=2,
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=2),
            status=ReservationStatus.ACTIVE,
        )
        Session.objects.create(
            restaurant=restaurant,
            table=table,
            reservation=active,
            guest_count=2,
            currency="UAH",
            opened_at=now - timedelta(minutes=30),
            ends_at=now + timedelta(hours=1),
            status=SessionStatus.OPEN,
        )

        # Pending booking at 21:30 — after the active session ends
        _check_reservation_conflict(
            restaurant_id=restaurant.id,
            table=table,
            start_at=now + timedelta(hours=1, minutes=30),
            end_at=now + timedelta(hours=2, minutes=30),
        )

    def test_active_prolong_not_self_rejected(
        self, restaurant: Restaurant, table: Table, restaurant_settings: RestaurantSettings, user_factory: Any
    ) -> None:
        """The active reservation's own prolong (start_at = session.opened_at) must not self-reject."""
        now = timezone.now()
        opened_at = now - timedelta(minutes=30)
        active = Reservation.objects.create(
            restaurant=restaurant,
            table=table,
            guest_count=2,
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=2),
            status=ReservationStatus.ACTIVE,
        )
        Session.objects.create(
            restaurant=restaurant,
            table=table,
            reservation=active,
            guest_count=2,
            currency="UAH",
            opened_at=opened_at,
            ends_at=now + timedelta(hours=1),
            status=SessionStatus.OPEN,
        )

        # Prolong: start_at = session.opened_at, end_at extended — should NOT self-reject
        _check_reservation_conflict(
            restaurant_id=restaurant.id,
            table=table,
            start_at=opened_at,
            end_at=now + timedelta(hours=3),
            current_reservation_id=active.id,
        )
