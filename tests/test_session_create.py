# mypy: disable-error-code="no-untyped-call"
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.orders.models import Session, SessionStatus
from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import Table, Zone

from .conftest import AuthContext

URL = reverse("session-list")


@pytest.mark.django_db(databases=["default"])
class TestSessionCreate:
    def test_waiter_can_create_walk_in_session(
        self,
        api: Callable[..., AuthContext],
        table: Table,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        response = auth.client.post(
            URL,
            {
                "table": str(table.public_id),
                "guest_count": 2,
                "opened_at": datetime.now(UTC).isoformat(),
                "currency": "UAH",
            },
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["table"] == str(table.public_id)
        assert data["status"] == "open"
        assert data["reservation"] is not None

        session = Session.objects.get(public_id=data["public_id"])
        assert session.status == SessionStatus.OPEN
        assert session.reservation is not None
        assert session.reservation.status == "active"
        assert session.reservation.type == "walk_in"

    def test_returns_409_when_table_already_has_open_session(
        self,
        api: Callable[..., AuthContext],
        table: Table,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        payload = {
            "table": str(table.public_id),
            "guest_count": 2,
            "opened_at": datetime.now(UTC).isoformat(),
            "currency": "UAH",
        }

        response = auth.client.post(URL, payload, content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED

        response = auth.client.post(URL, payload, content_type="application/json")
        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert data["code"] == "table_occupied"

    def test_stale_open_session_does_not_block_new_walk_in(
        self,
        api: Callable[..., AuthContext],
        table: Table,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        now = timezone.now()
        stale_reservation = Reservation.objects.create(
            restaurant=table.restaurant,
            table=table,
            guest_count=2,
            start_at=now - timedelta(days=1, hours=2),
            end_at=now - timedelta(days=1),
            status=ReservationStatus.ACTIVE,
        )
        Session.objects.create(
            restaurant=table.restaurant,
            table=table,
            reservation=stale_reservation,
            guest_count=2,
            status=SessionStatus.OPEN,
            currency="UAH",
            opened_at=stale_reservation.start_at,
            ends_at=stale_reservation.end_at,
        )
        payload = {
            "table": str(table.public_id),
            "guest_count": 2,
            "opened_at": datetime.now(UTC).isoformat(),
            "currency": "UAH",
        }

        response = auth.client.post(URL, payload, content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_recently_overdue_open_session_still_blocks_new_walk_in(
        self,
        api: Callable[..., AuthContext],
        table: Table,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        now = timezone.now()
        recent_reservation = Reservation.objects.create(
            restaurant=table.restaurant,
            table=table,
            guest_count=2,
            start_at=now - timedelta(hours=2),
            end_at=now - timedelta(minutes=10),
            status=ReservationStatus.ACTIVE,
        )
        Session.objects.create(
            restaurant=table.restaurant,
            table=table,
            reservation=recent_reservation,
            guest_count=2,
            status=SessionStatus.OPEN,
            currency="UAH",
            opened_at=recent_reservation.start_at,
            ends_at=recent_reservation.end_at + timedelta(hours=2),
        )
        payload = {
            "table": str(table.public_id),
            "guest_count": 2,
            "opened_at": datetime.now(UTC).isoformat(),
            "currency": "UAH",
        }

        response = auth.client.post(URL, payload, content_type="application/json")
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_prolonged_open_session_still_blocks_new_walk_in_without_being_closed(
        self,
        api: Callable[..., AuthContext],
        table: Table,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        now = timezone.now()
        reservation = Reservation.objects.create(
            restaurant=table.restaurant,
            table=table,
            guest_count=2,
            start_at=now - timedelta(hours=1),
            end_at=now - timedelta(minutes=5),
            status=ReservationStatus.ACTIVE,
        )
        session = Session.objects.create(
            restaurant=table.restaurant,
            table=table,
            reservation=reservation,
            guest_count=2,
            status=SessionStatus.OPEN,
            currency="UAH",
            opened_at=reservation.start_at,
            ends_at=now + timedelta(minutes=30),
        )
        session_id = session.pk
        original_ends_at = session.ends_at

        response = auth.client.post(
            URL,
            {
                "table": str(table.public_id),
                "guest_count": 2,
                "opened_at": datetime.now(UTC).isoformat(),
                "currency": "UAH",
            },
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        session.refresh_from_db()
        assert session.pk == session_id
        assert session.status == SessionStatus.OPEN
        assert session.ends_at == original_ends_at

    def test_returns_403_for_customer(
        self,
        api: Callable[..., AuthContext],
        table: Table,
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=table.restaurant_id)
        response = auth.client.post(
            URL,
            {
                "table": str(table.public_id),
                "guest_count": 2,
                "opened_at": datetime.now(UTC).isoformat(),
                "currency": "UAH",
            },
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db(databases=["default"])
class TestSessionPatch:
    def _open_session(self, client: Any, table: Table) -> dict[str, Any]:
        response = client.post(
            URL,
            {
                "table": str(table.public_id),
                "guest_count": 2,
                "opened_at": datetime.now(UTC).isoformat(),
                "currency": "UAH",
            },
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        return cast(dict[str, Any], response.json())

    def test_patch_table_is_ignored(
        self,
        api: Callable[..., AuthContext],
        table: Table,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        session = self._open_session(auth.client, table)
        session_id = str(session["public_id"])

        other_zone = Zone.objects.filter(restaurant=table.restaurant).first()
        assert other_zone is not None
        other_table = Table.objects.create(
            restaurant=table.restaurant,
            public_number="T2",
            capacity=4,
            zone=other_zone,
            active=True,
        )

        url = reverse("session-detail", kwargs={"public_id": session_id})
        response = auth.client.patch(
            url,
            {"table": str(other_table.public_id)},
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["table"] == str(table.public_id)

        refreshed = Session.objects.get(public_id=session_id)
        assert refreshed.table_id == table.id

    def test_patch_money_fields_are_ignored(
        self,
        api: Callable[..., AuthContext],
        table: Table,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        session = self._open_session(auth.client, table)
        session_id = str(session["public_id"])

        url = reverse("session-detail", kwargs={"public_id": session_id})
        before = Session.objects.get(public_id=session_id)

        response = auth.client.patch(
            url,
            {
                "subtotal": "999.99",
                "tax": "11.11",
                "service_charge": "7.00",
                "total": "1018.10",
                "currency": "USD",
            },
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_200_OK

        refreshed = Session.objects.get(public_id=session_id)
        assert refreshed.subtotal == before.subtotal
        assert refreshed.tax == before.tax
        assert refreshed.service_charge == before.service_charge
        assert refreshed.total == before.total
        assert refreshed.currency == before.currency
