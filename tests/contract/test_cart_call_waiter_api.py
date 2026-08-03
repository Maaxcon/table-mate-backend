from datetime import timedelta
from typing import Any
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.orders.models import CartSession
from apps.orders.services import ensure_active_cart_for_table
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Restaurant, Table


def _active_reservation(restaurant: Restaurant, table: Table) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now - timedelta(minutes=30),
        end_at=now + timedelta(hours=1),
        status=ReservationStatus.ACTIVE,
        type=ReservationType.PRE_BOOKED,
    )


def _guest_client(cart_session_id: Any, guest_id: str = "guest-1") -> APIClient:
    token = AccessToken()
    token.payload["is_guest"] = True
    token.payload["guest_id"] = guest_id
    token.payload["cart_session_id"] = str(cart_session_id)
    token.set_exp(lifetime=timedelta(hours=4))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _active_cart(restaurant: Restaurant, table: Table) -> CartSession:
    _active_reservation(restaurant, table)
    return ensure_active_cart_for_table(table=table)


@pytest.mark.django_db
def test_call_waiter_returns_204_and_notifies_staff(restaurant: Restaurant, table: Table) -> None:
    cart = _active_cart(restaurant, table)
    client = _guest_client(cart.public_id)
    url = reverse("cart-call-waiter", kwargs={"session_pk": cart.public_id})

    with mock.patch("apps.orders.services.sessions.emit_waiter_called") as emit:
        resp = client.post(url)

    assert resp.status_code == status.HTTP_204_NO_CONTENT
    emit.assert_called_once()
    _args, kwargs = emit.call_args
    assert kwargs["session_id"] == str(cart.public_id)
    assert kwargs["table_number"] == table.public_number


@pytest.mark.django_db
def test_call_waiter_second_call_within_cooldown_returns_429(
    restaurant: Restaurant, table: Table
) -> None:
    cart = _active_cart(restaurant, table)
    client = _guest_client(cart.public_id)
    url = reverse("cart-call-waiter", kwargs={"session_pk": cart.public_id})

    with mock.patch("apps.orders.services.sessions.emit_waiter_called") as emit:
        first = client.post(url)
        second = client.post(url)

    assert first.status_code == status.HTTP_204_NO_CONTENT
    assert second.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert second.json()["code"] == "waiter_call_cooldown"
    # The cooldown must actually suppress the second notification, not just
    # the HTTP response.
    emit.assert_called_once()


@pytest.mark.django_db
def test_call_waiter_different_tables_are_not_cross_throttled(
    restaurant: Restaurant, table: Table
) -> None:
    cart_a = _active_cart(restaurant, table)
    table_b = Table.objects.create(
        restaurant=restaurant, zone=table.zone, public_number="TB", capacity=4, active=True
    )
    cart_b = _active_cart(restaurant, table_b)

    with mock.patch("apps.orders.services.sessions.emit_waiter_called") as emit:
        client_a = _guest_client(cart_a.public_id)
        resp_a = client_a.post(reverse("cart-call-waiter", kwargs={"session_pk": cart_a.public_id}))
        client_b = _guest_client(cart_b.public_id)
        resp_b = client_b.post(reverse("cart-call-waiter", kwargs={"session_pk": cart_b.public_id}))

    assert resp_a.status_code == status.HTTP_204_NO_CONTENT
    assert resp_b.status_code == status.HTTP_204_NO_CONTENT
    assert emit.call_count == 2


@pytest.mark.django_db
def test_guest_token_cannot_call_waiter_for_other_table(
    restaurant: Restaurant, table: Table
) -> None:
    cart_a = _active_cart(restaurant, table)
    table_b = Table.objects.create(
        restaurant=restaurant, zone=table.zone, public_number="TB", capacity=4, active=True
    )
    cart_b = _active_cart(restaurant, table_b)

    client = _guest_client(cart_a.public_id)  # token scoped to table A's cart
    url = reverse("cart-call-waiter", kwargs={"session_pk": cart_b.public_id})

    with mock.patch("apps.orders.services.sessions.emit_waiter_called") as emit:
        resp = client.post(url)

    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    emit.assert_not_called()


@pytest.mark.django_db
def test_call_waiter_requires_authentication(restaurant: Restaurant, table: Table) -> None:
    cart = _active_cart(restaurant, table)
    url = reverse("cart-call-waiter", kwargs={"session_pk": cart.public_id})

    resp = APIClient().post(url)

    assert resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
