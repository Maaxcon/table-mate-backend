"""Served items are opt-in on the order-item list, and asked for explicitly.

The kitchen board only wants outstanding work; the waiter's table overlay
needs the whole bill. That used to be decided by whether an
order__session__public_id filter was *present* — an undeclared coupling that
also fired for an empty value matching nothing.
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.menu.models import MenuItem
from apps.orders.models import OrderItem, OrderItemStatus, Session, SessionStatus
from apps.orders.services import create_order_with_items
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Table

from .conftest import AuthContext

pytestmark = pytest.mark.django_db

ORDER_ITEM_LIST_URL = "/api/orders/order-items/"


def _served_session(table: Table, restaurant_id: int, actor: Any, item: MenuItem) -> Session:
    now = timezone.now()
    reservation = Reservation.objects.create(
        restaurant_id=restaurant_id,
        table=table,
        guest_count=2,
        start_at=now,
        end_at=now + timedelta(hours=2),
        status=ReservationStatus.ACTIVE,
        type=ReservationType.WALK_IN,
    )
    session = Session.objects.create(
        restaurant_id=restaurant_id,
        table=table,
        reservation=reservation,
        opened_by=actor,
        guest_count=2,
        currency="UAH",
        status=SessionStatus.OPEN,
        opened_at=now,
        ends_at=reservation.end_at,
    )
    create_order_with_items(
        session=session,
        items=[{"menu_item": item, "guest_slot": 1, "quantity": 1, "comment": None}],
        actor=actor,
    )
    OrderItem.objects.filter(order__session=session).update(status=OrderItemStatus.SERVED)
    return session


def _rows(resp: Any) -> list[dict[str, Any]]:
    payload = resp.json()
    return payload["results"] if isinstance(payload, dict) and "results" in payload else payload


def test_kitchen_board_does_not_see_served_items(
    api: Callable[..., AuthContext], restaurant: Any, table: Table, item: MenuItem
) -> None:
    auth = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
    _served_session(table, restaurant.id, auth.user, item)

    resp = auth.client.get(ORDER_ITEM_LIST_URL)

    assert resp.status_code == status.HTTP_200_OK
    assert _rows(resp) == []


def test_include_served_returns_the_whole_bill(
    api: Callable[..., AuthContext], restaurant: Any, table: Table, item: MenuItem
) -> None:
    auth = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
    _served_session(table, restaurant.id, auth.user, item)

    resp = auth.client.get(ORDER_ITEM_LIST_URL, {"include_served": "true"})

    assert resp.status_code == status.HTTP_200_OK
    assert len(_rows(resp)) == 1


def test_an_empty_session_filter_does_not_switch_behaviour(
    api: Callable[..., AuthContext], restaurant: Any, table: Table, item: MenuItem
) -> None:
    # The bug: presence alone flipped the exclusion off, so this matched
    # nothing yet still asked for served items across the restaurant.
    auth = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
    _served_session(table, restaurant.id, auth.user, item)

    resp = auth.client.get(ORDER_ITEM_LIST_URL, {"order__session__public_id": ""})

    assert resp.status_code == status.HTTP_200_OK
    assert _rows(resp) == []


def test_a_real_session_filter_still_returns_the_bill(
    api: Callable[..., AuthContext], restaurant: Any, table: Table, item: MenuItem
) -> None:
    # Honoured for clients deployed before include_served existed.
    auth = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
    session = _served_session(table, restaurant.id, auth.user, item)

    resp = auth.client.get(
        ORDER_ITEM_LIST_URL, {"order__session__public_id": str(session.public_id)}
    )

    assert resp.status_code == status.HTTP_200_OK
    assert len(_rows(resp)) == 1
