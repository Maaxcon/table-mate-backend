from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.orders.models import Order, Session
from apps.reservations.models import Reservation
from apps.restaurants.models import Restaurant, Table

from .conftest import AuthContext

URL = "/api/orders/orders/my/"


def _make_session(restaurant: Restaurant, table: Table, reservation: Reservation | None = None) -> Session:
    return Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=2,
        currency="UAH",
        started_at=timezone.now(),
    )


def _make_order(restaurant: Restaurant, session: Session, **kwargs: Any) -> Order:
    return Order.objects.create(
        restaurant=restaurant,
        session=session,
        currency="UAH",
        total_amount=Decimal("48.5000"),
        **kwargs,
    )


@pytest.mark.django_db
def test_my_returns_orders_created_by_customer(
    restaurant: Restaurant,
    table: Table,
    api: Callable[..., AuthContext],
) -> None:
    ctx = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
    session = _make_session(restaurant, table)
    own = _make_order(restaurant, session, created_by=ctx.user)

    res = ctx.client.get(URL)

    assert res.status_code == status.HTTP_200_OK
    assert [o["public_id"] for o in res.json()] == [str(own.public_id)]


@pytest.mark.django_db
def test_my_returns_orders_from_customer_reservation(
    restaurant: Restaurant,
    table: Table,
    api: Callable[..., AuthContext],
) -> None:
    ctx = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
    now = timezone.now()
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        customer=ctx.user,
        guest_count=2,
        start_at=now - timedelta(hours=2),
        end_at=now - timedelta(hours=1),
    )
    session = _make_session(restaurant, table, reservation=reservation)
    order = _make_order(restaurant, session)

    res = ctx.client.get(URL)

    assert res.status_code == status.HTTP_200_OK
    assert [o["public_id"] for o in res.json()] == [str(order.public_id)]


@pytest.mark.django_db
def test_my_excludes_other_customers_orders(
    restaurant: Restaurant,
    table: Table,
    api: Callable[..., AuthContext],
    user_factory: Callable[..., Any],
) -> None:
    ctx = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
    other = user_factory(role=RoleCode.CUSTOMER)
    other.save()
    session = _make_session(restaurant, table)
    _make_order(restaurant, session, created_by=other)

    res = ctx.client.get(URL)

    assert res.status_code == status.HTTP_200_OK
    assert res.json() == []


@pytest.mark.django_db
def test_my_requires_restaurant_context(
    api: Callable[..., AuthContext],
) -> None:
    # No restaurant_id => token has no restaurant claim => 400.
    ctx = api(role=RoleCode.CUSTOMER)

    res = ctx.client.get(URL)

    assert res.status_code == status.HTTP_400_BAD_REQUEST
