from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from typing import Any
from unittest import mock
from uuid import uuid4

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.menu.models import MenuItem
from apps.orders.billing import checkout_cart_session
from apps.orders.models import Order, OrderItem, OrderItemStatus, OrderPaymentStatus
from apps.orders.services import add_item_to_cart, ensure_active_cart_for_table
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Restaurant, Table


@pytest.fixture(autouse=True)
def _restaurant_open() -> Iterator[None]:
    # The working-hours fixture is keyed on real wall-clock time; pin the
    # restaurant open so these tests don't fail outside the configured hours.
    with (
        mock.patch("apps.orders.services.cart.is_restaurant_open", return_value=True),
        mock.patch("apps.orders.billing.is_restaurant_open", return_value=True),
    ):
        yield


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


def _ordered_visit(restaurant: Restaurant, table: Table, item: MenuItem) -> tuple[Any, Order]:
    """Active reservation + a submitted order of two `item` units; returns a fresh
    active cart (for the guest token) and the created order."""
    _active_reservation(restaurant, table)
    cart = ensure_active_cart_for_table(table=table)
    add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=2, guest_identity="guest-1")
    order = checkout_cart_session(cart_session=cart, user=None)
    fresh_cart = ensure_active_cart_for_table(table=table)
    return fresh_cart, order


@pytest.mark.django_db
def test_bill_lists_ordered_items(
    restaurant: Restaurant, table: Table, item: MenuItem, restaurant_settings: Any
) -> None:
    cart, _order = _ordered_visit(restaurant, table, item)

    client = _guest_client(cart.public_id)
    url = reverse("cart-bill", kwargs={"session_pk": cart.public_id})
    resp = client.get(url)

    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == item.name
    assert body[0]["is_paid"] is False
    # The bill the guest pays reconciles with what the order owes (goods + tax +
    # service), not just the goods subtotal.
    total_payable = sum((Decimal(row["payable"]) for row in body), Decimal("0"))
    assert total_payable == Order.objects.get().total_amount


@pytest.mark.django_db
def test_pay_marks_ordered_item_and_sets_order_paid(
    restaurant: Restaurant, table: Table, item: MenuItem, restaurant_settings: Any
) -> None:
    cart, order = _ordered_visit(restaurant, table, item)
    order_item = OrderItem.objects.get(order=order)

    client = _guest_client(cart.public_id)
    url = reverse("cart-pay", kwargs={"session_pk": cart.public_id})
    resp = client.post(url, {"order_item_ids": [str(order_item.public_id)]}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    order_item.refresh_from_db()
    order.refresh_from_db()
    assert order_item.is_paid is True
    # The order's only item is now paid, so the order flips to PAID.
    assert order.payment_status == OrderPaymentStatus.PAID


@pytest.mark.django_db
def test_guest_token_cannot_pay_other_table_bill(
    restaurant: Restaurant, table: Table, item: MenuItem, restaurant_settings: Any
) -> None:
    _active_reservation(restaurant, table)
    cart_a = ensure_active_cart_for_table(table=table)

    table_b = Table.objects.create(restaurant=restaurant, zone=table.zone, public_number="TB", capacity=4, active=True)
    cart_b, order_b = _ordered_visit(restaurant, table_b, item)
    order_item_b = OrderItem.objects.get(order=order_b)

    client = _guest_client(cart_a.public_id)  # token scoped to table A's cart
    url = reverse("cart-pay", kwargs={"session_pk": cart_b.public_id})
    resp = client.post(url, {"order_item_ids": [str(order_item_b.public_id)]}, format="json")

    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    order_item_b.refresh_from_db()
    assert order_item_b.is_paid is False


@pytest.mark.django_db
def test_guest_token_cannot_view_other_table_bill(
    restaurant: Restaurant, table: Table, item: MenuItem, restaurant_settings: Any
) -> None:
    _active_reservation(restaurant, table)
    cart_a = ensure_active_cart_for_table(table=table)

    table_b = Table.objects.create(restaurant=restaurant, zone=table.zone, public_number="TB", capacity=4, active=True)
    cart_b, _order_b = _ordered_visit(restaurant, table_b, item)

    client = _guest_client(cart_a.public_id)  # token scoped to table A's cart
    url = reverse("cart-bill", kwargs={"session_pk": cart_b.public_id})
    resp = client.get(url)

    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_pay_is_idempotent(
    restaurant: Restaurant, table: Table, item: MenuItem, restaurant_settings: Any
) -> None:
    cart, order = _ordered_visit(restaurant, table, item)
    order_item = OrderItem.objects.get(order=order)

    client = _guest_client(cart.public_id)
    url = reverse("cart-pay", kwargs={"session_pk": cart.public_id})
    payload = {"order_item_ids": [str(order_item.public_id)]}

    first = client.post(url, payload, format="json")
    second = client.post(url, payload, format="json")

    # Paying an already-paid item is a no-op, not an error.
    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    order_item.refresh_from_db()
    order.refresh_from_db()
    assert order_item.is_paid is True
    assert order.payment_status == OrderPaymentStatus.PAID


@pytest.mark.django_db
def test_pay_ignores_unknown_item_ids(
    restaurant: Restaurant, table: Table, item: MenuItem, restaurant_settings: Any
) -> None:
    cart, order = _ordered_visit(restaurant, table, item)
    order_item = OrderItem.objects.get(order=order)

    client = _guest_client(cart.public_id)
    url = reverse("cart-pay", kwargs={"session_pk": cart.public_id})
    resp = client.post(url, {"order_item_ids": [str(uuid4())]}, format="json")

    # An id that belongs to no item on this visit touches nothing.
    assert resp.status_code == status.HTTP_200_OK
    order_item.refresh_from_db()
    order.refresh_from_db()
    assert order_item.is_paid is False
    assert order.payment_status == OrderPaymentStatus.UNPAID


@pytest.mark.django_db
def test_pay_excludes_voided_item(
    restaurant: Restaurant, table: Table, item: MenuItem, restaurant_settings: Any
) -> None:
    cart, order = _ordered_visit(restaurant, table, item)
    order_item = OrderItem.objects.get(order=order)
    order_item.status = OrderItemStatus.VOIDED
    order_item.save(update_fields=["status"])

    client = _guest_client(cart.public_id)
    url = reverse("cart-pay", kwargs={"session_pk": cart.public_id})
    resp = client.post(url, {"order_item_ids": [str(order_item.public_id)]}, format="json")

    # A voided item is not payable, so it stays unpaid.
    assert resp.status_code == status.HTTP_200_OK
    order_item.refresh_from_db()
    assert order_item.is_paid is False
