from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.menu.models import MenuItem
from apps.orders.billing import close_visit_session, ensure_visit_session
from apps.orders.models import (
    CartSessionStatus,
    CreatedBySource,
    Order,
    OrderItem,
    OrderItemStatus,
    OrderSource,
    OrderStatus,
    SessionStatus,
)
from apps.receipts.models import Receipt
from apps.orders.services import ensure_active_cart_for_table
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.reservations.selectors import get_active_reservation_for_table
from apps.restaurants.models import Restaurant, Table


def _active_reservation(restaurant: Restaurant, table: Table) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now - timedelta(minutes=10),
        end_at=now + timedelta(hours=1),
        status=ReservationStatus.ACTIVE,
        type=ReservationType.PRE_BOOKED,
    )


@pytest.mark.django_db
def test_close_frees_the_table(restaurant: Restaurant, table: Table) -> None:
    reservation = _active_reservation(restaurant, table)
    session = ensure_visit_session(reservation)
    cart = ensure_active_cart_for_table(table=table)

    close_visit_session(session=session)

    session.refresh_from_db()
    reservation.refresh_from_db()
    cart.refresh_from_db()
    assert session.status == SessionStatus.CLOSED
    assert reservation.status == ReservationStatus.COMPLETED
    assert cart.status == CartSessionStatus.CLOSED
    assert get_active_reservation_for_table(table) is None


@pytest.mark.django_db
def test_close_is_idempotent(restaurant: Restaurant, table: Table) -> None:
    reservation = _active_reservation(restaurant, table)
    session = ensure_visit_session(reservation)

    close_visit_session(session=session)
    close_visit_session(session=session)  # must not raise

    session.refresh_from_db()
    assert session.status == SessionStatus.CLOSED


@pytest.mark.django_db
def test_close_endpoint_returns_200_and_closes(
    restaurant: Restaurant,
    table: Table,
    api: Callable[..., Any],
) -> None:
    reservation = _active_reservation(restaurant, table)
    session = ensure_visit_session(reservation)
    staff = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)

    resp = staff.client.post(f"/api/orders/sessions/{session.public_id}/close/")

    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["status"] == SessionStatus.CLOSED
    reservation.refresh_from_db()
    assert reservation.status == ReservationStatus.COMPLETED


@pytest.mark.django_db
def test_close_creates_receipt_with_dishes_for_waiter_walk_in(
    restaurant: Restaurant,
    table: Table,
    item: MenuItem,
    user_factory: Callable[..., Any],
) -> None:
    waiter = user_factory(role=RoleCode.WAITER)
    waiter.save()
    reservation = _active_reservation(restaurant, table)
    session = ensure_visit_session(reservation, opened_by=waiter)
    order = Order.objects.create(
        restaurant=restaurant,
        session=session,
        created_by=waiter,
        created_by_source=CreatedBySource.STAFF,
        source=OrderSource.WAITER_MANUAL,
        currency="UAH",
        total_amount=Decimal("59.9800"),
    )
    OrderItem.objects.create(
        restaurant=restaurant,
        order=order,
        menu_item=item,
        guest_slot=1,
        quantity=2,
        status=OrderItemStatus.SERVED,
        unit_price=Decimal("29.9900"),
        total_price=Decimal("59.9800"),
    )

    close_visit_session(session=session, actor=waiter)

    order.refresh_from_db()
    assert order.status == OrderStatus.COMPLETED
    receipt = Receipt.objects.get(order=order)
    assert receipt.customer_id == waiter.pk
    assert receipt.items.count() == 1
    receipt_item = receipt.items.get()
    assert receipt_item.name == item.name
    assert receipt_item.quantity == 2
    assert receipt_item.unit_price == Decimal("29.99")
