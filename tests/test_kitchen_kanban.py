# mypy: disable-error-code="no-untyped-call"
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from django.urls import reverse
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.menu.models import MenuItem
from apps.orders.models import (
    OrderItemStatus,
    Session,
    TicketStatus,
)
from apps.orders.selectors import (
    compute_avg_prep_time,
    get_kitchen_order_items,
    get_kitchen_tickets,
)
from apps.orders.services import create_order_with_items, open_session
from apps.restaurants.models import Table

from .conftest import AuthContext

ORDER_LIST_URL = reverse("order-list")
SESSION_LIST_URL = reverse("session-list")
TICKET_LIST_URL = reverse("ticket-list")
ORDER_ITEM_LIST_URL = reverse("order-item-list")


def _create_session(client: Any, table: Table, restaurant_id: int) -> dict[str, Any]:
    response = client.post(
        SESSION_LIST_URL,
        {
            "table": str(table.public_id),
            "guest_count": 4,
            "opened_at": datetime.now(UTC).isoformat(),
            "currency": "UAH",
        },
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = cast(dict[str, Any], response.json())
    return data


def _build_session(table: Table, restaurant_id: int, user: Any) -> Session:
    return open_session(
        restaurant_id=restaurant_id,
        table=table,
        guest_count=4,
        opened_by=user,
        currency="UAH",
        opened_at=datetime.now(UTC).isoformat(),
        actor=user,
    )


@pytest.mark.django_db(databases=["default"])
class TestKitchenSelectors:
    def test_get_kitchen_tickets_annotated(
        self,
        api: Callable[..., AuthContext],
        restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.WAITER)
        actor = auth.user
        restaurant_id = restaurant.id

        session = _build_session(table, restaurant_id, actor)
        create_order_with_items(
            session=session,
            items=[
                {"menu_item": item, "guest_slot": 1, "quantity": 2, "comment": None},
            ],
            actor=actor,
        )

        tickets = get_kitchen_tickets(restaurant_id)
        assert len(tickets) == 1
        ticket = tickets[0]
        annotated = cast(Any, ticket)
        assert ticket.status == TicketStatus.INCOMING
        assert annotated.table_number == table.table_number
        assert annotated.server_name == actor.get_full_name()
        assert annotated.guest_count == session.guest_count
        assert annotated.items_count > 0

    def test_get_kitchen_tickets_filter_by_status(
        self,
        api: Callable[..., AuthContext],
        restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.WAITER)
        actor = auth.user
        restaurant_id = restaurant.id

        session = _build_session(table, restaurant_id, actor)
        create_order_with_items(
            session=session,
            items=[{"menu_item": item, "guest_slot": 1, "quantity": 1, "comment": None}],
            actor=actor,
        )

        incoming = get_kitchen_tickets(restaurant_id, status="incoming")
        assert len(incoming) == 1

        active = get_kitchen_tickets(restaurant_id, status="active")
        assert len(active) == 0

    def test_get_kitchen_tickets_empty_restaurant(
        self,
        empty_restaurant: Any,
    ) -> None:
        tickets = get_kitchen_tickets(empty_restaurant.id)
        assert tickets == []

    def test_get_kitchen_order_items_by_ticket(
        self,
        api: Callable[..., AuthContext],
        restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.WAITER)
        actor = auth.user
        restaurant_id = restaurant.id

        session = _build_session(table, restaurant_id, actor)
        order = create_order_with_items(
            session=session,
            items=[{"menu_item": item, "guest_slot": 1, "quantity": 2, "comment": None}],
            actor=actor,
        )

        ticket = order.tickets.first()
        assert ticket is not None

        items = get_kitchen_order_items(restaurant_id, ticket_id=str(ticket.public_id))
        assert len(items) == 1
        assert items[0].menu_item.name == item.name
        assert items[0].status == OrderItemStatus.PENDING

    def test_get_kitchen_order_items_filter_by_status(
        self,
        api: Callable[..., AuthContext],
        restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.WAITER)
        actor = auth.user
        restaurant_id = restaurant.id

        session = _build_session(table, restaurant_id, actor)
        order = create_order_with_items(
            session=session,
            items=[{"menu_item": item, "guest_slot": 1, "quantity": 2, "comment": None}],
            actor=actor,
        )
        ticket = order.tickets.first()
        assert ticket is not None
        order_item = ticket.items.first()
        assert order_item is not None

        order_item.status = OrderItemStatus.READY
        order_item.save(update_fields=["status"])

        pending = get_kitchen_order_items(restaurant_id, ticket_id=str(ticket.public_id), status="pending")
        assert len(pending) == 0

        ready = get_kitchen_order_items(restaurant_id, ticket_id=str(ticket.public_id), status="ready")
        assert len(ready) == 1

    def test_compute_avg_prep_time_no_completed_tickets(
        self,
        restaurant: Any,
    ) -> None:
        avg = compute_avg_prep_time(restaurant.id)
        assert avg is None

    def test_compute_avg_prep_time_with_completed_tickets(
        self,
        api: Callable[..., AuthContext],
        restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.WAITER)
        actor = auth.user
        restaurant_id = restaurant.id

        session = _build_session(table, restaurant_id, actor)
        order = create_order_with_items(
            session=session,
            items=[{"menu_item": item, "guest_slot": 1, "quantity": 1, "comment": None}],
            actor=actor,
        )
        ticket = order.tickets.first()
        assert ticket is not None

        ticket.status = TicketStatus.COMPLETED
        ticket.started_at = ticket.injected_at
        ticket.completed_at = ticket.injected_at + timedelta(minutes=10)
        ticket.save(update_fields=["status", "started_at", "completed_at"])

        avg = compute_avg_prep_time(restaurant_id)
        assert avg is not None
        assert avg == pytest.approx(600.0, rel=0.1)


@pytest.mark.django_db(databases=["default"])
class TestTicketKanbanAPI:
    def test_full_kanban_workflow(
        self,
        api: Callable[..., AuthContext],
        restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
        actor = auth.user
        client = auth.client
        restaurant_id = restaurant.id

        session = _build_session(table, restaurant_id, actor)
        order = create_order_with_items(
            session=session,
            items=[{"menu_item": item, "guest_slot": 1, "quantity": 2, "comment": None}],
            actor=actor,
        )
        ticket = order.tickets.first()
        assert ticket is not None
        public_id = str(ticket.public_id)

        ticket_url = reverse("ticket-detail", kwargs={"public_id": public_id})

        resp = client.get(ticket_url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == TicketStatus.INCOMING
        assert data["table_number"] == table.table_number
        assert "server_name" in data
        assert data["guest_count"] == 4
        assert data["items_count"] > 0

        resp = client.patch(
            ticket_url,
            {"status": "active", "started_at": datetime.now(UTC).isoformat()},
            content_type="application/json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == TicketStatus.ACTIVE

        order_item = ticket.items.first()
        assert order_item is not None
        item_url = reverse("order-item-detail", kwargs={"public_id": str(order_item.public_id)})
        resp = client.patch(
            item_url,
            {"status": "ready"},
            content_type="application/json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == OrderItemStatus.READY

        remaining = ticket.items.exclude(public_id=order_item.public_id).first()
        if remaining:
            remaining_url = reverse("order-item-detail", kwargs={"public_id": str(remaining.public_id)})
            resp = client.patch(
                remaining_url,
                {"status": "ready"},
                content_type="application/json",
            )
            assert resp.status_code == status.HTTP_200_OK

        resp = client.patch(
            ticket_url,
            {"status": "completed", "completed_at": datetime.now(UTC).isoformat()},
            content_type="application/json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == TicketStatus.COMPLETED

    def test_list_tickets_filtered_by_status(
        self,
        api: Callable[..., AuthContext],
        restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.COOK, restaurant_id=restaurant.id)
        client = auth.client
        restaurant_id = restaurant.id
        actor = auth.user

        session = _build_session(table, restaurant_id, actor)
        create_order_with_items(
            session=session,
            items=[{"menu_item": item, "guest_slot": 1, "quantity": 1, "comment": None}],
            actor=actor,
        )

        resp = client.get(TICKET_LIST_URL, {"status": "incoming"})
        assert resp.status_code == status.HTTP_200_OK
        results = resp.json()["results"] if "results" in resp.json() else resp.json()
        assert len(results) == 1
        assert results[0]["status"] == TicketStatus.INCOMING

    def test_cook_can_patch_ticket_status(
        self,
        api: Callable[..., AuthContext],
        restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.COOK, restaurant_id=restaurant.id)
        client = auth.client
        restaurant_id = restaurant.id
        actor = auth.user

        session = _build_session(table, restaurant_id, actor)
        order = create_order_with_items(
            session=session,
            items=[{"menu_item": item, "guest_slot": 1, "quantity": 1, "comment": None}],
            actor=actor,
        )
        ticket = order.tickets.first()
        assert ticket is not None

        ticket_url = reverse("ticket-detail", kwargs={"public_id": str(ticket.public_id)})
        resp = client.patch(
            ticket_url,
            {"status": "active", "started_at": datetime.now(UTC).isoformat()},
            content_type="application/json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == TicketStatus.ACTIVE

    def test_cook_can_patch_order_item_status(
        self,
        api: Callable[..., AuthContext],
        restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.COOK, restaurant_id=restaurant.id)
        client = auth.client
        restaurant_id = restaurant.id
        actor = auth.user

        session = _build_session(table, restaurant_id, actor)
        order = create_order_with_items(
            session=session,
            items=[{"menu_item": item, "guest_slot": 1, "quantity": 1, "comment": None}],
            actor=actor,
        )
        order_item = order.items.first()
        assert order_item is not None

        item_url = reverse("order-item-detail", kwargs={"public_id": str(order_item.public_id)})
        resp = client.patch(
            item_url,
            {"status": "ready"},
            content_type="application/json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == OrderItemStatus.READY


@pytest.mark.django_db(databases=["default"])
class TestTicketStatusTransitions:
    def test_incoming_to_active(
        self,
        api: Callable[..., AuthContext],
        restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.COOK, restaurant_id=restaurant.id)
        client = auth.client
        actor = auth.user
        restaurant_id = restaurant.id

        session = _build_session(table, restaurant_id, actor)
        order = create_order_with_items(
            session=session,
            items=[{"menu_item": item, "guest_slot": 1, "quantity": 1, "comment": None}],
            actor=actor,
        )
        ticket = order.tickets.first()
        assert ticket is not None

        ticket_url = reverse("ticket-detail", kwargs={"public_id": str(ticket.public_id)})

        resp = client.patch(
            ticket_url,
            {"status": "active", "started_at": datetime.now(UTC).isoformat()},
            content_type="application/json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == "active"

    def test_active_to_completed(
        self,
        api: Callable[..., AuthContext],
        restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.COOK, restaurant_id=restaurant.id)
        client = auth.client
        actor = auth.user
        restaurant_id = restaurant.id

        session = _build_session(table, restaurant_id, actor)
        order = create_order_with_items(
            session=session,
            items=[{"menu_item": item, "guest_slot": 1, "quantity": 1, "comment": None}],
            actor=actor,
        )
        ticket = order.tickets.first()
        assert ticket is not None
        ticket.status = TicketStatus.ACTIVE
        ticket.started_at = datetime.now(UTC)
        ticket.save(update_fields=["status", "started_at"])

        ticket_url = reverse("ticket-detail", kwargs={"public_id": str(ticket.public_id)})
        resp = client.patch(
            ticket_url,
            {"status": "completed", "completed_at": datetime.now(UTC).isoformat()},
            content_type="application/json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == "completed"
