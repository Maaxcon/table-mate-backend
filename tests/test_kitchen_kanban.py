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
TICKET_STATS_URL = reverse("ticket-stats")


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

        tickets = list(get_kitchen_tickets(restaurant_id))
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

        incoming = list(get_kitchen_tickets(restaurant_id, status="incoming"))
        assert len(incoming) == 1

        active = list(get_kitchen_tickets(restaurant_id, status="active"))
        assert len(active) == 0

    def test_get_kitchen_tickets_empty_restaurant(
        self,
        empty_restaurant: Any,
    ) -> None:
        tickets = list(get_kitchen_tickets(empty_restaurant.id))
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

        items = list(get_kitchen_order_items(restaurant_id, ticket_id=str(ticket.public_id)))
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

        pending = list(get_kitchen_order_items(restaurant_id, ticket_id=str(ticket.public_id), status="pending"))
        assert len(pending) == 0

        ready = list(get_kitchen_order_items(restaurant_id, ticket_id=str(ticket.public_id), status="ready"))
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
        auth = api(role=RoleCode.COOK, restaurant_id=restaurant.id)
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

    def test_waiter_can_list_ticket_api(
        self,
        api: Callable[..., AuthContext],
        restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
        client = auth.client
        actor = auth.user
        restaurant_id = restaurant.id

        session = _build_session(table, restaurant_id, actor)
        create_order_with_items(
            session=session,
            items=[{"menu_item": item, "guest_slot": 1, "quantity": 1, "comment": None}],
            actor=actor,
        )

        resp = client.get(TICKET_LIST_URL)
        assert resp.status_code == status.HTTP_200_OK
        payload = resp.json()
        results = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
        assert len(results) == 1

    def test_waiter_cannot_update_ticket_or_items(
        self,
        api: Callable[..., AuthContext],
        restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
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
            {"status": "active"},
            content_type="application/json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

        order_item = ticket.items.first()
        assert order_item is not None
        item_url = reverse("order-item-detail", kwargs={"public_id": str(order_item.public_id)})
        resp = client.patch(
            item_url,
            {"status": "ready"},
            content_type="application/json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_waiter_can_list_order_items(
        self,
        api: Callable[..., AuthContext],
        restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
        client = auth.client
        actor = auth.user
        restaurant_id = restaurant.id

        session = _build_session(table, restaurant_id, actor)
        create_order_with_items(
            session=session,
            items=[{"menu_item": item, "guest_slot": 1, "quantity": 2, "comment": None}],
            actor=actor,
        )

        resp = client.get(
            ORDER_ITEM_LIST_URL,
            {"order__session__public_id": str(session.public_id)},
        )
        assert resp.status_code == status.HTTP_200_OK
        payload = resp.json()
        results = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
        assert len(results) >= 1

    def test_ticket_list_fifo_counts_and_server_name_sanitized(
        self,
        api: Callable[..., AuthContext],
        restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        cook = api(role=RoleCode.COOK, restaurant_id=restaurant.id)
        waiter = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
        waiter_user = waiter.user
        waiter_user.first_name = ""
        waiter_user.last_name = ""
        waiter_user.save(update_fields=["first_name", "last_name"])

        session = _build_session(table, restaurant.id, waiter_user)
        order = create_order_with_items(
            session=session,
            items=[
                {"menu_item": item, "guest_slot": 1, "quantity": 1, "comment": None},
                {"menu_item": item, "guest_slot": 2, "quantity": 1, "comment": None},
            ],
            actor=waiter_user,
        )
        first_ticket = order.tickets.first()
        assert first_ticket is not None
        void_candidate = first_ticket.items.first()
        assert void_candidate is not None
        void_candidate.status = OrderItemStatus.VOIDED
        void_candidate.save(update_fields=["status"])

        later_order = create_order_with_items(
            session=session,
            items=[{"menu_item": item, "guest_slot": 1, "quantity": 1, "comment": None}],
            actor=waiter_user,
        )
        second_ticket = later_order.tickets.first()
        assert second_ticket is not None

        resp = cook.client.get(TICKET_LIST_URL)
        assert resp.status_code == status.HTTP_200_OK
        payload = resp.json()
        results = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
        assert len(results) >= 2
        assert [row["public_id"] for row in results[:2]] == [
            str(first_ticket.public_id),
            str(second_ticket.public_id),
        ]
        assert results[0]["items_count"] == 1
        assert results[0]["server_name"] == ""

    def test_ticket_stats_returns_avg_prep_time(
        self,
        api: Callable[..., AuthContext],
        restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.COOK, restaurant_id=restaurant.id)
        client = auth.client
        user = auth.user
        session = _build_session(table, restaurant.id, user)
        order = create_order_with_items(
            session=session,
            items=[{"menu_item": item, "guest_slot": 1, "quantity": 1, "comment": None}],
            actor=user,
        )
        ticket = order.tickets.first()
        assert ticket is not None
        ticket.status = TicketStatus.COMPLETED
        ticket.injected_at = datetime.now(UTC) - timedelta(minutes=12)
        ticket.completed_at = ticket.injected_at + timedelta(minutes=6)
        ticket.save(update_fields=["status", "injected_at", "completed_at"])

        resp = client.get(TICKET_STATS_URL)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["avg_prep_time_seconds"] == pytest.approx(360.0, rel=0.1)

    def test_waiter_can_mark_order_item_served(
        self,
        api: Callable[..., AuthContext],
        restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        waiter = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
        client = waiter.client
        user = waiter.user
        session = _build_session(table, restaurant.id, user)
        order = create_order_with_items(
            session=session,
            items=[{"menu_item": item, "guest_slot": 1, "quantity": 1, "comment": None}],
            actor=user,
        )
        order_item = order.items.first()
        assert order_item is not None
        order_item.status = OrderItemStatus.READY
        order_item.save(update_fields=["status"])

        item_url = reverse("order-item-detail", kwargs={"public_id": str(order_item.public_id)})
        resp = client.patch(
            item_url,
            {"status": OrderItemStatus.SERVED},
            content_type="application/json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == OrderItemStatus.SERVED

    def test_waiter_cannot_mark_item_ready(
        self,
        api: Callable[..., AuthContext],
        restaurant: Any,
        table: Table,
        item: MenuItem,
    ) -> None:
        waiter = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
        client = waiter.client
        user = waiter.user
        session = _build_session(table, restaurant.id, user)
        order = create_order_with_items(
            session=session,
            items=[{"menu_item": item, "guest_slot": 1, "quantity": 1, "comment": None}],
            actor=user,
        )
        order_item = order.items.first()
        assert order_item is not None

        item_url = reverse("order-item-detail", kwargs={"public_id": str(order_item.public_id)})
        resp = client.patch(
            item_url,
            {"status": OrderItemStatus.READY},
            content_type="application/json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

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
