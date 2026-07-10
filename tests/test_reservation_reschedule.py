from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.orders.models import Session, SessionStatus
from apps.reservations.models import Reservation, ReservationStatus
from apps.reservations.services import check_availability
from apps.restaurants.models import Restaurant, Table

from .conftest import AuthContext


@pytest.mark.django_db
def test_check_availability_excludes_current_reservation(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
) -> None:
    customer = user_factory(role=RoleCode.CUSTOMER)
    customer.save()
    start_at = timezone.now() + timedelta(hours=1)
    end_at = start_at + timedelta(hours=2)
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        customer=customer,
        table=table,
        guest_count=2,
        start_at=start_at,
        end_at=end_at,
        status=ReservationStatus.PENDING,
    )

    assert not check_availability(
        restaurant_id=restaurant.id,
        table_id=str(table.public_id),
        start_at=start_at,
        end_at=end_at,
    )
    assert check_availability(
        restaurant_id=restaurant.id,
        table_id=str(table.public_id),
        start_at=start_at,
        end_at=end_at,
        current_reservation_id=reservation.id,
    )


@pytest.mark.django_db
def test_customer_can_reschedule_own_reservation_without_self_conflict(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
    api_factory: Callable[..., AuthContext],
) -> None:
    customer = user_factory(role=RoleCode.CUSTOMER)
    customer.save()
    start_at = timezone.now() + timedelta(hours=1)
    end_at = start_at + timedelta(hours=2)
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        customer=customer,
        table=table,
        guest_count=2,
        start_at=start_at,
        end_at=end_at,
        status=ReservationStatus.PENDING,
    )
    client, _ = api_factory(user=customer, restaurant_id=restaurant.id)

    response = client.patch(
        f"/api/reservations/reservations/{reservation.public_id}/",
        {"end_at": (end_at + timedelta(minutes=30)).isoformat()},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    reservation.refresh_from_db()
    assert reservation.end_at == end_at + timedelta(minutes=30)


@pytest.mark.django_db
def test_customer_cannot_reschedule_another_customers_reservation(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
    api_factory: Callable[..., AuthContext],
) -> None:
    owner = user_factory(role=RoleCode.CUSTOMER)
    owner.save()
    other_customer = user_factory(role=RoleCode.CUSTOMER)
    other_customer.save()
    start_at = timezone.now() + timedelta(hours=1)
    end_at = start_at + timedelta(hours=2)
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        customer=owner,
        table=table,
        guest_count=2,
        start_at=start_at,
        end_at=end_at,
        status=ReservationStatus.PENDING,
    )
    client, _ = api_factory(user=other_customer, restaurant_id=restaurant.id)

    response = client.patch(
        f"/api/reservations/reservations/{reservation.public_id}/",
        {"end_at": (end_at + timedelta(minutes=30)).isoformat()},
        format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    reservation.refresh_from_db()
    assert reservation.end_at == end_at


def _active_reservation(restaurant: Restaurant, table: Table, customer: Any) -> Reservation:
    start_at = timezone.now() - timedelta(minutes=10)
    res = Reservation.objects.create(
        restaurant=restaurant,
        customer=customer,
        table=table,
        guest_count=2,
        start_at=start_at,
        end_at=start_at + timedelta(hours=2),
        status=ReservationStatus.ACTIVE,
    )
    from apps.orders.models import Session, SessionStatus

    Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=res,
        guest_count=2,
        currency="UAH",
        opened_at=start_at,
        ends_at=res.end_at,
        status=SessionStatus.OPEN,
    )
    return res


@pytest.mark.django_db
def test_customer_can_prolong_active_reservation(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
    api_factory: Callable[..., AuthContext],
) -> None:
    from apps.orders.models import Session, SessionStatus

    customer = user_factory(role=RoleCode.CUSTOMER)
    customer.save()
    reservation = _active_reservation(restaurant, table, customer)
    session = Session.objects.get(reservation=reservation, status=SessionStatus.OPEN)
    original_session_end = session.ends_at
    client, _ = api_factory(user=customer, restaurant_id=restaurant.id)

    new_end = original_session_end + timedelta(minutes=30)
    response = client.patch(
        f"/api/reservations/reservations/{reservation.public_id}/",
        {"end_at": new_end.isoformat()},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    session.refresh_from_db()
    assert session.ends_at == new_end


@pytest.mark.django_db
def test_customer_can_prolong_active_reservation_with_open_session(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
    api_factory: Callable[..., AuthContext],
) -> None:
    """Activating a reservation always opens a Session on its table (see
    activate_reservation). A guest prolonging that same reservation must not
    have their own session's grace-cutoff block the extension as a false
    self-conflict — regression test for that exact bug.
    """
    customer = user_factory(role=RoleCode.CUSTOMER)
    customer.save()
    reservation = _active_reservation(restaurant, table, customer)
    Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=reservation.guest_count,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=reservation.start_at,
    )
    original_end = reservation.end_at
    client, _ = api_factory(user=customer, restaurant_id=restaurant.id)

    response = client.patch(
        f"/api/reservations/reservations/{reservation.public_id}/",
        {"end_at": (original_end + timedelta(minutes=30)).isoformat()},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    reservation.refresh_from_db()
    assert reservation.end_at == original_end + timedelta(minutes=30)


@pytest.mark.django_db
def test_customer_cannot_reschedule_active_reservation_start_time(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
    api_factory: Callable[..., AuthContext],
) -> None:
    """Active reservations cannot change start_at, only end_at."""
    customer = user_factory(role=RoleCode.CUSTOMER)
    customer.save()
    reservation = _active_reservation(restaurant, table, customer)
    original_end = reservation.end_at
    client, _ = api_factory(user=customer, restaurant_id=restaurant.id)

    response = client.patch(
        f"/api/reservations/reservations/{reservation.public_id}/",
        {
            "start_at": (reservation.start_at + timedelta(hours=1)).isoformat(),
            "end_at": (original_end + timedelta(minutes=30)).isoformat(),
        },
        format="json",
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    reservation.refresh_from_db()
    assert reservation.end_at == original_end


@pytest.mark.django_db
def test_customer_cannot_cancel_active_reservation(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
    api_factory: Callable[..., AuthContext],
) -> None:
    customer = user_factory(role=RoleCode.CUSTOMER)
    customer.save()
    reservation = _active_reservation(restaurant, table, customer)
    client, _ = api_factory(user=customer, restaurant_id=restaurant.id)

    response = client.patch(
        f"/api/reservations/reservations/{reservation.public_id}/",
        {"status": "cancelled"},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    reservation.refresh_from_db()
    assert reservation.status == ReservationStatus.ACTIVE


@pytest.mark.django_db
def test_my_reservations_filters_active_records_and_supports_limit_offset(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
    api_factory: Callable[..., AuthContext],
) -> None:
    customer = user_factory(role=RoleCode.CUSTOMER)
    customer.save()
    base_start = timezone.now() + timedelta(hours=1)
    statuses = [
        ReservationStatus.PENDING,
        ReservationStatus.ACTIVE,
        ReservationStatus.COMPLETED,
        ReservationStatus.CANCELLED,
        ReservationStatus.PENDING,
    ]
    for index, reservation_status in enumerate(statuses):
        start_at = base_start + timedelta(hours=index * 3)
        Reservation.objects.create(
            restaurant=restaurant,
            customer=customer,
            table=table,
            guest_count=2,
            start_at=start_at,
            end_at=start_at + timedelta(hours=2),
            status=reservation_status,
        )
    client, _ = api_factory(user=customer, restaurant_id=restaurant.id)

    response = client.get("/api/reservations/reservations/my/?limit=2&offset=1")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 2
    assert [item["status"] for item in data] == [
        ReservationStatus.ACTIVE,
        ReservationStatus.PENDING,
    ]
    assert data[0]["restaurant_info"]["name"] == restaurant.name
    assert data[0]["table_info"]["public_number"] == table.public_number


@pytest.mark.django_db
def test_my_reservations_status_past_returns_history_newest_first(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
    api_factory: Callable[..., AuthContext],
) -> None:
    customer = user_factory(role=RoleCode.CUSTOMER)
    customer.save()
    base_start = timezone.now() - timedelta(days=10)
    statuses = [
        ReservationStatus.PENDING,
        ReservationStatus.ACTIVE,
        ReservationStatus.COMPLETED,
        ReservationStatus.CANCELLED,
    ]
    for index, reservation_status in enumerate(statuses):
        start_at = base_start + timedelta(days=index)
        Reservation.objects.create(
            restaurant=restaurant,
            customer=customer,
            table=table,
            guest_count=2,
            start_at=start_at,
            end_at=start_at + timedelta(hours=2),
            status=reservation_status,
        )
    client, _ = api_factory(user=customer, restaurant_id=restaurant.id)

    response = client.get("/api/reservations/reservations/my/?status=past")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    # Only completed/cancelled, newest start_at first (cancelled is day 3, completed day 2).
    assert [item["status"] for item in data] == [
        ReservationStatus.CANCELLED,
        ReservationStatus.COMPLETED,
    ]
