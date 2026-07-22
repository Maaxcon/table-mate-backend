from collections.abc import Callable, Iterator
from datetime import timedelta
from decimal import Decimal
from typing import Any
from unittest import mock

import pytest
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.menu.models import MenuItem
from apps.orders.billing import checkout_cart_session, close_visit_session, ensure_visit_session
from apps.orders.models import Order, OrderItem, OrderItemStatus, OrderPaymentStatus, SessionStatus
from apps.orders.services import add_item_to_cart, ensure_active_cart_for_table
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Restaurant, Table


@pytest.fixture(autouse=True)
def _restaurant_open() -> Iterator[None]:
    # The working-hours fixture is keyed on real wall-clock time; pin the
    # restaurant open so these tests don't fail outside the configured hours.
    with mock.patch("apps.orders.services.cart.is_restaurant_open", return_value=True):
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


def _ordered_visit(restaurant: Restaurant, table: Table, item: MenuItem, quantity: int = 2) -> tuple[Any, Order]:
    reservation = _active_reservation(restaurant, table)
    session = ensure_visit_session(reservation)
    cart = ensure_active_cart_for_table(table=table)
    add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=quantity, guest_identity="guest-1")
    order = checkout_cart_session(cart_session=cart, user=None)
    return session, order


@pytest.mark.django_db
def test_pay_endpoint_marks_all_outstanding_items_paid(
    restaurant: Restaurant,
    table: Table,
    item: MenuItem,
    restaurant_settings: Any,
    api: Callable[..., Any],
) -> None:
    session, order = _ordered_visit(restaurant, table, item)
    staff = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)

    resp = staff.client.post(f"/api/orders/sessions/{session.public_id}/pay/")

    assert resp.status_code == status.HTTP_200_OK
    order_item = OrderItem.objects.get(order=order)
    order.refresh_from_db()
    assert order_item.is_paid is True
    assert order.payment_status == OrderPaymentStatus.PAID


@pytest.mark.django_db
def test_pay_endpoint_is_idempotent(
    restaurant: Restaurant,
    table: Table,
    item: MenuItem,
    restaurant_settings: Any,
    api: Callable[..., Any],
) -> None:
    session, order = _ordered_visit(restaurant, table, item)
    staff = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
    url = f"/api/orders/sessions/{session.public_id}/pay/"

    first = staff.client.post(url)
    second = staff.client.post(url)

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    order.refresh_from_db()
    assert order.payment_status == OrderPaymentStatus.PAID


@pytest.mark.django_db
def test_pay_endpoint_excludes_voided_items(
    restaurant: Restaurant,
    table: Table,
    item: MenuItem,
    restaurant_settings: Any,
    api: Callable[..., Any],
) -> None:
    session, order = _ordered_visit(restaurant, table, item)
    order_item = OrderItem.objects.get(order=order)
    order_item.status = OrderItemStatus.VOIDED
    order_item.save(update_fields=["status"])
    staff = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)

    resp = staff.client.post(f"/api/orders/sessions/{session.public_id}/pay/")

    assert resp.status_code == status.HTTP_200_OK
    order_item.refresh_from_db()
    assert order_item.is_paid is False


@pytest.mark.django_db
def test_pay_endpoint_pays_only_selected_items(
    restaurant: Restaurant,
    table: Table,
    item: MenuItem,
    restaurant_settings: Any,
    api: Callable[..., Any],
) -> None:
    reservation = _active_reservation(restaurant, table)
    session = ensure_visit_session(reservation)
    cart = ensure_active_cart_for_table(table=table)
    other_item = MenuItem.objects.create(
        menu=item.menu,
        category=item.category,
        restaurant=restaurant,
        name="Fries",
        price=Decimal("5.00"),
        sort_order=2,
    )
    add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=1, guest_identity="guest-1")
    add_item_to_cart(session=cart, menu_item_id=str(other_item.public_id), quantity=1, guest_identity="guest-1")
    order = checkout_cart_session(cart_session=cart, user=None)
    paid_target = OrderItem.objects.get(order=order, menu_item=item)
    left_unpaid = OrderItem.objects.get(order=order, menu_item=other_item)
    staff = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)

    resp = staff.client.post(
        f"/api/orders/sessions/{session.public_id}/pay/",
        {"order_item_ids": [str(paid_target.public_id)]},
        format="json",
    )

    assert resp.status_code == status.HTTP_200_OK
    paid_target.refresh_from_db()
    left_unpaid.refresh_from_db()
    assert paid_target.is_paid is True
    assert left_unpaid.is_paid is False


@pytest.mark.django_db
def test_pay_endpoint_rejects_closed_session(
    restaurant: Restaurant,
    table: Table,
    item: MenuItem,
    restaurant_settings: Any,
    api: Callable[..., Any],
) -> None:
    session, order = _ordered_visit(restaurant, table, item)
    OrderItem.objects.filter(order=order).update(status=OrderItemStatus.SERVED)
    close_visit_session(session=session)
    staff = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)

    resp = staff.client.post(f"/api/orders/sessions/{session.public_id}/pay/")

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    session.refresh_from_db()
    assert session.status == SessionStatus.CLOSED
