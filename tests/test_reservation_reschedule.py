from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
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
