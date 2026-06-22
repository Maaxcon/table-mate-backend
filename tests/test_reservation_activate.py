from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.orders.models import CartSessionStatus, Session
from apps.orders.services import ensure_active_cart_for_table
from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import Restaurant, Table


def _reservation(
    restaurant: Restaurant,
    table: Table,
    *,
    customer: Any = None,
    res_status: str = ReservationStatus.PENDING,
    start_offset: timedelta = timedelta(hours=1),
) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        customer=customer,
        guest_count=2,
        start_at=now + start_offset,
        end_at=now + start_offset + timedelta(hours=2),
        status=res_status,
    )


def _url(reservation: Reservation) -> str:
    return f"/api/reservations/reservations/{reservation.public_id}/activate/"


@pytest.mark.django_db
def test_staff_activates_pending_reservation(
    restaurant: Restaurant,
    table: Table,
    api: Callable[..., Any],
) -> None:
    reservation = _reservation(restaurant, table)
    staff = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)

    resp = staff.client.post(_url(reservation))

    assert resp.status_code == status.HTTP_200_OK
    reservation.refresh_from_db()
    assert reservation.status == ReservationStatus.ACTIVE
    # Variant 2: activation opens the visit Session (bill) right away.
    assert Session.objects.filter(reservation=reservation).count() == 1


@pytest.mark.django_db
def test_activate_does_not_duplicate_session(
    restaurant: Restaurant,
    table: Table,
    api: Callable[..., Any],
) -> None:
    reservation = _reservation(restaurant, table)
    staff = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)

    staff.client.post(_url(reservation))
    staff.client.post(_url(reservation))

    assert Session.objects.filter(reservation=reservation).count() == 1


@pytest.mark.django_db
def test_owner_customer_activates_own_reservation(
    restaurant: Restaurant,
    table: Table,
    api: Callable[..., Any],
) -> None:
    customer_ctx = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
    # Within the early window: booking starts in 10 minutes.
    reservation = _reservation(
        restaurant, table, customer=customer_ctx.user, start_offset=timedelta(minutes=10)
    )

    resp = customer_ctx.client.post(_url(reservation))

    assert resp.status_code == status.HTTP_200_OK
    reservation.refresh_from_db()
    assert reservation.status == ReservationStatus.ACTIVE


@pytest.mark.django_db
def test_customer_cannot_activate_far_future_reservation(
    restaurant: Restaurant,
    table: Table,
    api: Callable[..., Any],
) -> None:
    # Booking is hours away: a guest must not open it early. Staff still can.
    customer_ctx = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
    reservation = _reservation(
        restaurant, table, customer=customer_ctx.user, start_offset=timedelta(hours=2)
    )

    resp = customer_ctx.client.post(_url(reservation))

    assert resp.status_code == status.HTTP_409_CONFLICT
    reservation.refresh_from_db()
    assert reservation.status == ReservationStatus.PENDING
    assert not Session.objects.filter(reservation=reservation).exists()


@pytest.mark.django_db
def test_staff_can_activate_far_future_reservation(
    restaurant: Restaurant,
    table: Table,
    api: Callable[..., Any],
) -> None:
    # Same far-future booking, but staff have no time limit.
    reservation = _reservation(restaurant, table, start_offset=timedelta(hours=2))
    staff = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)

    resp = staff.client.post(_url(reservation))

    assert resp.status_code == status.HTTP_200_OK
    reservation.refresh_from_db()
    assert reservation.status == ReservationStatus.ACTIVE


@pytest.mark.django_db
def test_customer_cannot_activate_other_reservation(
    restaurant: Restaurant,
    table: Table,
    api: Callable[..., Any],
    user_factory: Callable[..., Any],
) -> None:
    owner = user_factory(role=RoleCode.CUSTOMER)
    owner.save()
    reservation = _reservation(restaurant, table, customer=owner)

    intruder = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
    resp = intruder.client.post(_url(reservation))

    assert resp.status_code == status.HTTP_404_NOT_FOUND
    reservation.refresh_from_db()
    assert reservation.status == ReservationStatus.PENDING


@pytest.mark.django_db
def test_activate_is_idempotent_when_already_active(
    restaurant: Restaurant,
    table: Table,
    api: Callable[..., Any],
) -> None:
    reservation = _reservation(restaurant, table, res_status=ReservationStatus.ACTIVE)
    staff = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)

    resp = staff.client.post(_url(reservation))

    assert resp.status_code == status.HTTP_200_OK
    reservation.refresh_from_db()
    assert reservation.status == ReservationStatus.ACTIVE


@pytest.mark.django_db
def test_cannot_activate_cancelled_reservation(
    restaurant: Restaurant,
    table: Table,
    api: Callable[..., Any],
) -> None:
    reservation = _reservation(restaurant, table, res_status=ReservationStatus.CANCELLED)
    staff = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)

    resp = staff.client.post(_url(reservation))

    assert resp.status_code == status.HTTP_409_CONFLICT
    reservation.refresh_from_db()
    assert reservation.status == ReservationStatus.CANCELLED


@pytest.mark.django_db
def test_staff_cannot_activate_reservation_in_other_restaurant(
    restaurant: Restaurant,
    table: Table,
    api: Callable[..., Any],
) -> None:
    # Reservation lives in restaurant A.
    reservation = _reservation(restaurant, table)

    # A waiter scoped to a different restaurant must not reach it. The only tenant
    # guard is get_queryset(), so a regression there would silently allow this.
    other = Restaurant.objects.create(name="Other", address="9 Other St")
    staff_b = api(role=RoleCode.WAITER, restaurant_id=other.id)

    resp = staff_b.client.post(_url(reservation))

    assert resp.status_code == status.HTTP_404_NOT_FOUND
    reservation.refresh_from_db()
    assert reservation.status == ReservationStatus.PENDING


@pytest.mark.django_db
def test_activated_reservation_yields_cart(
    restaurant: Restaurant,
    table: Table,
    api: Callable[..., Any],
) -> None:
    # Booking time has arrived, so the activated reservation is time-valid for ensure.
    reservation = _reservation(restaurant, table, start_offset=timedelta(minutes=-10))
    staff = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)

    resp = staff.client.post(_url(reservation))
    assert resp.status_code == status.HTTP_200_OK

    cart = ensure_active_cart_for_table(table=table)
    assert cart.status == CartSessionStatus.ACTIVE
    assert cart.reservation_id == reservation.id
