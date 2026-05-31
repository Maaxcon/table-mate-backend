from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.receipts.models import PaymentMethod, Receipt, ReceiptItem
from apps.restaurants.models import Restaurant

from .conftest import AuthContext

URL = "/api/receipts/my/"


def _make_receipt(customer: Any, restaurant: Restaurant, order_number: str = "TM-1") -> Receipt:
    receipt = Receipt.objects.create(
        customer=customer,
        restaurant=restaurant,
        order_number=order_number,
        visited_at=datetime(2026, 5, 18, 19, 30, tzinfo=UTC),
        currency="USD",
        table_label="Table 7",
        server_name="Olena K.",
        guests=2,
        tax=Decimal("4.25"),
        service_charge=Decimal("4.25"),
        tip=Decimal("6.00"),
        payment_method=PaymentMethod.CARD,
    )
    ReceiptItem.objects.create(receipt=receipt, name="Steak", quantity=1, unit_price=Decimal("24.50"))
    ReceiptItem.objects.create(receipt=receipt, name="Lemonade", quantity=2, unit_price=Decimal("4.50"))
    return receipt


@pytest.mark.django_db
def test_my_returns_own_receipts(
    restaurant: Restaurant,
    api: Callable[..., AuthContext],
) -> None:
    ctx = api(role=RoleCode.CUSTOMER)
    _make_receipt(ctx.user, restaurant)

    res = ctx.client.get(URL)

    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert len(data) == 1
    row = data[0]
    assert row["order_number"] == "TM-1"
    assert row["restaurant_name"] == restaurant.name
    assert len(row["items"]) == 2
    # subtotal 24.50 + 9.00 = 33.50; total = 33.50 + 4.25 + 4.25 + 6.00 = 48.00
    assert row["subtotal"] == "33.50"
    assert row["total"] == "48.00"
    assert row["payment_method"] == "card"


@pytest.mark.django_db
def test_my_excludes_other_users(
    restaurant: Restaurant,
    api: Callable[..., AuthContext],
    user_factory: Callable[..., Any],
) -> None:
    ctx = api(role=RoleCode.CUSTOMER)
    other = user_factory(role=RoleCode.CUSTOMER)
    other.save()
    _make_receipt(other, restaurant, order_number="TM-OTHER")

    res = ctx.client.get(URL)

    assert res.status_code == status.HTTP_200_OK
    assert res.json() == []


@pytest.mark.django_db
def test_my_requires_auth() -> None:
    from rest_framework.test import APIClient

    res = APIClient().get(URL)
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
