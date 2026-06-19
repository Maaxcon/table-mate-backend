from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.orders.models import CartItem, CartSessionStatus, Order
from apps.orders.services import add_item_to_cart, ensure_active_cart_for_table
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


@pytest.mark.django_db
def test_checkout_success_returns_order_and_closes_cart(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    _active_reservation(restaurant, table)
    cart = ensure_active_cart_for_table(table=table)
    add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=2, guest_identity="guest-1")

    client = _guest_client(cart.public_id)
    url = reverse("cart-checkout", kwargs={"session_pk": cart.public_id})
    resp = client.post(url)

    assert resp.status_code == status.HTTP_201_CREATED
    assert "order_id" in resp.json()
    assert Order.objects.count() == 1
    cart.refresh_from_db()
    assert cart.status == CartSessionStatus.CLOSED


@pytest.mark.django_db
def test_checkout_unavailable_item_returns_409_cart_changed(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    _active_reservation(restaurant, table)
    cart = ensure_active_cart_for_table(table=table)
    add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=1, guest_identity="guest-1")
    item.is_available = False
    item.save(update_fields=["is_available"])

    client = _guest_client(cart.public_id)
    url = reverse("cart-checkout", kwargs={"session_pk": cart.public_id})
    resp = client.post(url)

    assert resp.status_code == status.HTTP_409_CONFLICT
    body = resp.json()
    assert body["code"] == "CART_CHANGED"
    assert [r["name"] for r in body["removed"]] == [item.name]
    cart.refresh_from_db()
    assert cart.status == CartSessionStatus.ACTIVE
    assert not Order.objects.exists()
    assert not CartItem.objects.filter(cart_session=cart).exists()


@pytest.mark.django_db
def test_checkout_empty_cart_returns_400(
    restaurant: Restaurant,
    table: Table,
    restaurant_settings: Any,
) -> None:
    _active_reservation(restaurant, table)
    cart = ensure_active_cart_for_table(table=table)

    client = _guest_client(cart.public_id)
    url = reverse("cart-checkout", kwargs={"session_pk": cart.public_id})
    resp = client.post(url)

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.json()["code"] == "empty_cart"


@pytest.mark.django_db
def test_guest_token_cannot_checkout_other_session(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    _active_reservation(restaurant, table)
    cart_a = ensure_active_cart_for_table(table=table)

    table_b = Table.objects.create(restaurant=restaurant, table_number="TB", capacity=4, active=True)
    _active_reservation(restaurant, table_b)
    cart_b = ensure_active_cart_for_table(table=table_b)
    add_item_to_cart(session=cart_b, menu_item_id=str(item.public_id), quantity=1)

    client = _guest_client(cart_a.public_id)  # token scoped to cart A
    url = reverse("cart-checkout", kwargs={"session_pk": cart_b.public_id})
    resp = client.post(url)

    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert not Order.objects.exists()


@pytest.mark.django_db
def test_authenticated_non_participant_cannot_checkout(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
    api: Callable[..., Any],
) -> None:
    _active_reservation(restaurant, table)
    cart = ensure_active_cart_for_table(table=table)
    add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=1, guest_identity="guest-1")

    # A logged-in customer whose token carries the same restaurant but who is
    # not a participant of this cart must not be able to check it out.
    outsider = api(restaurant_id=restaurant.id)
    url = reverse("cart-checkout", kwargs={"session_pk": cart.public_id})
    resp = outsider.client.post(url)

    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert not Order.objects.exists()
    cart.refresh_from_db()
    assert cart.status == CartSessionStatus.ACTIVE
