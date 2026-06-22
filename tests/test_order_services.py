# mypy: disable-error-code="no-untyped-call"
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from django.urls import reverse
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.menu.models import MenuItem
from apps.orders.models import (
    Order,
    OrderItem,
    OrderItemStatus,
    Session,
    SessionStatus,
    Ticket,
    TicketStatus,
)
from apps.restaurants.models import Table

from .conftest import AuthContext

ORDER_LIST_URL = reverse("order-list")
SESSION_LIST_URL = reverse("session-list")
ORDER_ITEM_VOID_URL = "order-item-void"


def _create_session(client: Any, table: Table, restaurant_id: int) -> Any:
    response = client.post(
        SESSION_LIST_URL,
        {
            "table": str(table.public_id),
            "guest_count": 2,
            "opened_at": datetime.now(UTC).isoformat(),
            "currency": "UAH",
        },
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


def _build_session(
    table: Table,
    restaurant_id: int,
    user: Any,
    status_override: str | None = None,
) -> Session:
    from apps.orders.services import open_session

    session = open_session(
        restaurant_id=restaurant_id,
        table=table,
        guest_count=2,
        opened_by=user,
        currency="UAH",
        opened_at=datetime.now(UTC).isoformat(),
        actor=user,
    )
    if status_override:
        session.status = status_override
        session.save(update_fields=["status"])
        session.refresh_from_db()
    return session


@pytest.mark.django_db(databases=["default"])
class TestCreateOrderWithItems:
    def test_success(
        self,
        api: Callable[..., AuthContext],
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        session_data = _create_session(auth.client, table, table.restaurant_id)

        payload = {
            "session": session_data["public_id"],
            "items": [
                {
                    "menu_item": str(item.public_id),
                    "guest_slot": 1,
                    "quantity": 2,
                    "comment": "medium rare",
                },
            ],
        }
        response = auth.client.post(ORDER_LIST_URL, payload, content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED, response.json()
        data = response.json()

        assert data["session"] == session_data["public_id"]
        assert data["currency"] == "UAH"
        assert data["source"] == "waiter_manual"
        assert data["status"] == "submitted"

        order = Order.objects.get(public_id=data["public_id"])
        assert order.total_amount == Decimal("59.98")  # 29.99 * 2

        ticket = Ticket.objects.get(order=order)
        assert ticket.session_id == order.session_id
        assert ticket.status == TicketStatus.INCOMING

        items = list(OrderItem.objects.filter(order=order))
        assert len(items) == 1
        item_obj = items[0]
        assert item_obj.quantity == 2
        assert item_obj.unit_price == Decimal("29.99")
        assert item_obj.total_price == Decimal("59.98")
        assert item_obj.comment == "medium rare"
        assert item_obj.ticket == ticket

        session = Session.objects.get(public_id=session_data["public_id"])
        assert session.subtotal == Decimal("59.9800")
        assert session.total == session.subtotal

    def test_multiple_items(
        self,
        api: Callable[..., AuthContext],
        table: Table,
        item: MenuItem,
        menu: Any,
        category: Any,
        restaurant: Any,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        session_data = _create_session(auth.client, table, table.restaurant_id)

        item2 = MenuItem.objects.create(
            menu=menu,
            category=category,
            restaurant=restaurant,
            name="Salad",
            price=Decimal("15.50"),
            sort_order=2,
        )

        payload = {
            "session": session_data["public_id"],
            "items": [
                {"menu_item": str(item.public_id), "quantity": 1},
                {"menu_item": str(item2.public_id), "quantity": 3},
            ],
        }
        response = auth.client.post(ORDER_LIST_URL, payload, content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED, response.json()

        order = Order.objects.get(public_id=response.json()["public_id"])
        assert order.total_amount == Decimal("76.49")  # 29.99 + 15.50 * 3

    def test_rejects_non_open_session(
        self,
        api: Callable[..., AuthContext],
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)

        session = _build_session(table, table.restaurant_id, auth.user, status_override=SessionStatus.CLOSED)

        payload = {
            "session": str(session.public_id),
            "items": [{"menu_item": str(item.public_id), "quantity": 1}],
        }
        response = auth.client.post(ORDER_LIST_URL, payload, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_session_from_different_restaurant(
        self,
        api: Callable[..., AuthContext],
        empty_restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=empty_restaurant.id)

        payload = {
            "session": str(table.restaurant_id),  # won't exist — different restaurant
            "items": [{"menu_item": str(item.public_id), "quantity": 1}],
        }
        response = auth.client.post(ORDER_LIST_URL, payload, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_nonexistent_menu_item(
        self,
        api: Callable[..., AuthContext],
        table: Table,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        session_data = _create_session(auth.client, table, table.restaurant_id)

        payload = {
            "session": session_data["public_id"],
            "items": [{"menu_item": "00000000-0000-0000-0000-000000000000", "quantity": 1}],
        }
        response = auth.client.post(ORDER_LIST_URL, payload, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_request_without_items_field(
        self,
        api: Callable[..., AuthContext],
        table: Table,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        session_data = _create_session(auth.client, table, table.restaurant_id)

        payload = {
            "session": session_data["public_id"],
        }
        response = auth.client.post(ORDER_LIST_URL, payload, content_type="application/json")
        # No items field — falls through to super().create() which expects session
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_recomputes_session_totals_after_multiple_orders(
        self,
        api: Callable[..., AuthContext],
        table: Table,
        item: MenuItem,
        menu: Any,
        category: Any,
        restaurant: Any,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        session_data = _create_session(auth.client, table, table.restaurant_id)

        item2 = MenuItem.objects.create(
            menu=menu,
            category=category,
            restaurant=restaurant,
            name="Salad",
            price=Decimal("15.50"),
            sort_order=2,
        )

        auth.client.post(
            ORDER_LIST_URL,
            {
                "session": session_data["public_id"],
                "items": [{"menu_item": str(item.public_id), "quantity": 1}],
            },
            content_type="application/json",
        )

        auth.client.post(
            ORDER_LIST_URL,
            {
                "session": session_data["public_id"],
                "items": [{"menu_item": str(item2.public_id), "quantity": 2}],
            },
            content_type="application/json",
        )

        session = Session.objects.get(public_id=session_data["public_id"])
        assert session.subtotal == Decimal("60.9900")  # 29.99 + 31.00
        assert session.total == session.subtotal

    def test_creates_guest_slot_defaults_to_one(
        self,
        api: Callable[..., AuthContext],
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        session_data = _create_session(auth.client, table, table.restaurant_id)

        payload = {
            "session": session_data["public_id"],
            "items": [{"menu_item": str(item.public_id), "quantity": 1}],
        }
        response = auth.client.post(ORDER_LIST_URL, payload, content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED

        order = Order.objects.get(public_id=response.json()["public_id"])
        order_item = OrderItem.objects.filter(order=order).first()
        assert order_item is not None
        assert order_item.guest_slot == 1


@pytest.mark.django_db(databases=["default"])
class TestVoidOrderItem:
    def test_success(
        self,
        api: Callable[..., AuthContext],
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        session_data = _create_session(auth.client, table, table.restaurant_id)

        order_resp = auth.client.post(
            ORDER_LIST_URL,
            {
                "session": session_data["public_id"],
                "items": [{"menu_item": str(item.public_id), "quantity": 2}],
            },
            content_type="application/json",
        )
        assert order_resp.status_code == status.HTTP_201_CREATED

        order_item = OrderItem.objects.filter(order__public_id=order_resp.json()["public_id"]).first()
        assert order_item is not None

        url = reverse(ORDER_ITEM_VOID_URL, kwargs={"public_id": order_item.public_id})
        response = auth.client.post(url, {"void_reason": "mispick"}, content_type="application/json")
        assert response.status_code == status.HTTP_200_OK, response.json()
        data = response.json()
        assert data["status"] == "voided"
        assert data["void_reason"] == "mispick"

        order_item.refresh_from_db()
        assert order_item.status == OrderItemStatus.VOIDED

        order = Order.objects.get(public_id=order_resp.json()["public_id"])
        assert order.total_amount == Decimal("0")

        session = Session.objects.get(public_id=session_data["public_id"])
        assert session.subtotal == Decimal("0")
        assert session.tax == Decimal("0")
        assert session.total == Decimal("0")

    def test_rejects_double_void(
        self,
        api: Callable[..., AuthContext],
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        session_data = _create_session(auth.client, table, table.restaurant_id)

        order_resp = auth.client.post(
            ORDER_LIST_URL,
            {
                "session": session_data["public_id"],
                "items": [{"menu_item": str(item.public_id), "quantity": 1}],
            },
            content_type="application/json",
        )
        assert order_resp.status_code == status.HTTP_201_CREATED

        order_item = OrderItem.objects.filter(order__public_id=order_resp.json()["public_id"]).first()
        assert order_item is not None

        url = reverse(ORDER_ITEM_VOID_URL, kwargs={"public_id": order_item.public_id})
        first = auth.client.post(url, {"void_reason": "mispick"}, content_type="application/json")
        assert first.status_code == status.HTTP_200_OK

        second = auth.client.post(url, {"void_reason": "mispick"}, content_type="application/json")
        assert second.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_invalid_void_reason(
        self,
        api: Callable[..., AuthContext],
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        session_data = _create_session(auth.client, table, table.restaurant_id)

        order_resp = auth.client.post(
            ORDER_LIST_URL,
            {
                "session": session_data["public_id"],
                "items": [{"menu_item": str(item.public_id), "quantity": 1}],
            },
            content_type="application/json",
        )
        assert order_resp.status_code == status.HTTP_201_CREATED

        order_item = OrderItem.objects.filter(order__public_id=order_resp.json()["public_id"]).first()
        assert order_item is not None

        url = reverse(ORDER_ITEM_VOID_URL, kwargs={"public_id": order_item.public_id})
        response = auth.client.post(url, {"void_reason": "bogus_reason"}, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_with_note(
        self,
        api: Callable[..., AuthContext],
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=table.restaurant_id)
        session_data = _create_session(auth.client, table, table.restaurant_id)

        order_resp = auth.client.post(
            ORDER_LIST_URL,
            {
                "session": session_data["public_id"],
                "items": [{"menu_item": str(item.public_id), "quantity": 1}],
            },
            content_type="application/json",
        )
        assert order_resp.status_code == status.HTTP_201_CREATED

        order_item = OrderItem.objects.filter(order__public_id=order_resp.json()["public_id"]).first()
        assert order_item is not None

        url = reverse(ORDER_ITEM_VOID_URL, kwargs={"public_id": order_item.public_id})
        response = auth.client.post(
            url,
            {"void_reason": "quality_issue", "note": "Burnt to a crisp"},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["void_reason_note"] == "Burnt to a crisp"

        session = Session.objects.get(public_id=session_data["public_id"])
        assert session.subtotal == Decimal("0")
        assert session.tax == Decimal("0")
        assert session.total == Decimal("0")
