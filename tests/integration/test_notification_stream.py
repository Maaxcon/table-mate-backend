from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator

from apps.authentication.models import RoleCode
from apps.authentication.services import issue_tokens_with_restaurant
from apps.editor.consumers import (
    FloorConsumer,
    NotificationStreamConsumer,
    _filter_event_for_floor,
)
from common.channels import staff_group_name
from common.notification_events import (
    emit_cart_created,
    emit_kitchen_ticket_injected,
    emit_order_item_status_changed,
)
from core.routing import application
from tests.conftest import RestaurantFactory, UserFactory


@pytest.fixture(autouse=True)
def _inmemory_channel_layer(settings: Any) -> None:
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }


# ── NotificationStreamConsumer auth / role gates ──


@pytest.mark.django_db
def test_notification_consumer_rejects_unauthenticated() -> None:
    async def _test() -> None:
        communicator = WebsocketCommunicator(NotificationStreamConsumer.as_asgi(), "/ws/staff/notifications/")
        await communicator.connect()
        close_code = await communicator.receive_output(timeout=5)
        assert close_code["type"] == "websocket.close"
        assert close_code["code"] == 4001

    asyncio.run(_test())


@pytest.mark.django_db
def test_notification_consumer_rejects_customer(restaurant: Any) -> None:
    async def _test() -> None:
        user = UserFactory.build(role=RoleCode.CUSTOMER)
        await sync_to_async(user.save)()
        access, _ = await sync_to_async(issue_tokens_with_restaurant)(user, restaurant.id)
        communicator = WebsocketCommunicator(
            application,
            "/ws/staff/notifications/",
            subprotocols=["access_token", access],
        )
        connected, _ = await communicator.connect()
        assert connected
        close_code = await communicator.receive_output(timeout=5)
        assert close_code["type"] == "websocket.close"
        assert close_code["code"] == 4003

    asyncio.run(_test())


@pytest.mark.django_db
def test_notification_consumer_allows_waiter(restaurant: Any) -> None:
    async def _test() -> None:
        user = UserFactory.build(role=RoleCode.WAITER)
        await sync_to_async(user.save)()
        access, _ = await sync_to_async(issue_tokens_with_restaurant)(user, restaurant.id)
        communicator = WebsocketCommunicator(
            application,
            "/ws/staff/notifications/",
            subprotocols=["access_token", access],
        )
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    asyncio.run(_test())


@pytest.mark.django_db
def test_notification_consumer_allows_admin(restaurant: Any) -> None:
    async def _test() -> None:
        user = UserFactory.build(role=RoleCode.ADMIN)
        await sync_to_async(user.save)()
        access, _ = await sync_to_async(issue_tokens_with_restaurant)(user, restaurant.id)
        communicator = WebsocketCommunicator(
            application,
            "/ws/staff/notifications/",
            subprotocols=["access_token", access],
        )
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    asyncio.run(_test())


@pytest.mark.django_db
def test_notification_consumer_allows_cook(restaurant: Any) -> None:
    async def _test() -> None:
        user = UserFactory.build(role=RoleCode.COOK)
        await sync_to_async(user.save)()
        access, _ = await sync_to_async(issue_tokens_with_restaurant)(user, restaurant.id)
        communicator = WebsocketCommunicator(
            application,
            "/ws/staff/notifications/",
            subprotocols=["access_token", access],
        )
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    asyncio.run(_test())


# ── Tenant isolation (staff_A never receives staff_B) ──


@pytest.mark.django_db(databases=["default"], transaction=True)
def test_notification_tenant_isolation(restaurant: Any) -> None:
    async def _test() -> None:
        other_restaurant: Any = await sync_to_async(RestaurantFactory)(name="Other Restaurant")

        waiter = UserFactory.build(role=RoleCode.WAITER)
        await sync_to_async(waiter.save)()
        other_waiter = UserFactory.build(role=RoleCode.WAITER)
        await sync_to_async(other_waiter.save)()

        access, _ = await sync_to_async(issue_tokens_with_restaurant)(waiter, restaurant.id)
        other_access, _ = await sync_to_async(issue_tokens_with_restaurant)(other_waiter, other_restaurant.id)

        comm = WebsocketCommunicator(
            application,
            "/ws/staff/notifications/",
            subprotocols=["access_token", access],
        )
        other_comm = WebsocketCommunicator(
            application,
            "/ws/staff/notifications/",
            subprotocols=["access_token", other_access],
        )

        connected, _ = await comm.connect()
        assert connected
        connected, _ = await other_comm.connect()
        assert connected

        await sync_to_async(emit_cart_created)(
            restaurant.id,
            session_id="session-A",
            table_number="T1",
            guest_name="Alice",
        )

        event = await comm.receive_json_from(timeout=3)
        assert event["type"] == "CART_CREATED"

        with pytest.raises(asyncio.TimeoutError):
            await other_comm.receive_json_from(timeout=0.5)

        await comm.disconnect()
        try:
            await other_comm.disconnect()
        except asyncio.CancelledError:
            pass

    asyncio.run(_test())


# ── _filter_event_for_floor ──


class TestFilterEventForFloor:
    def test_keeps_allowed_fields_for_table_status_changed(self) -> None:
        event = {
            "event_name": "HALL_TABLE_STATUS_CHANGED",
            "schema_version": "1",
            "event_id": "abc-123",
            "table_id": "table-uuid",
            "current_status": "occupied",
            "session_id": "session-uuid",
            "actor_id": 1,
            "actor_role": "waiter",
            "occurred_at": "2026-06-22T10:00:00Z",
        }
        filtered = _filter_event_for_floor(event)
        assert filtered == {
            "event_name": "HALL_TABLE_STATUS_CHANGED",
            "table_id": "table-uuid",
            "current_status": "occupied",
            "occurred_at": "2026-06-22T10:00:00Z",
        }
        assert "session_id" not in filtered
        assert "actor_id" not in filtered
        assert "actor_role" not in filtered
        assert "schema_version" not in filtered
        assert "event_id" not in filtered

    def test_keeps_allowed_fields_for_new_reservation(self) -> None:
        event = {
            "event_name": "HALL_NEW_RESERVATION",
            "schema_version": "1",
            "event_id": "abc-123",
            "table_id": "table-uuid",
            "reservation_id": "res-uuid",
            "start_at": "2026-06-22T18:00:00Z",
            "end_at": "2026-06-22T20:00:00Z",
            "session_id": "session-uuid",
            "actor_id": 1,
            "actor_role": "waiter",
            "occurred_at": "2026-06-22T10:00:00Z",
        }
        filtered = _filter_event_for_floor(event)
        assert filtered == {
            "event_name": "HALL_NEW_RESERVATION",
            "table_id": "table-uuid",
            "reservation_id": "res-uuid",
            "start_at": "2026-06-22T18:00:00Z",
            "end_at": "2026-06-22T20:00:00Z",
            "occurred_at": "2026-06-22T10:00:00Z",
        }
        assert "session_id" not in filtered
        assert "actor_id" not in filtered
        assert "actor_role" not in filtered

    def test_keeps_allowed_fields_for_reservation_cancelled(self) -> None:
        event = {
            "event_name": "HALL_RESERVATION_CANCELLED",
            "schema_version": "1",
            "event_id": "abc-123",
            "table_id": "table-uuid",
            "session_id": "session-uuid",
            "actor_id": 1,
            "actor_role": "admin",
            "occurred_at": "2026-06-22T10:00:00Z",
        }
        filtered = _filter_event_for_floor(event)
        assert filtered == {
            "event_name": "HALL_RESERVATION_CANCELLED",
            "table_id": "table-uuid",
            "occurred_at": "2026-06-22T10:00:00Z",
        }
        assert "session_id" not in filtered
        assert "actor_id" not in filtered
        assert "actor_role" not in filtered

    def test_returns_empty_for_unknown_event(self) -> None:
        event: dict[str, object] = {"event_name": "UNKNOWN_EVENT", "some_field": "value"}
        filtered = _filter_event_for_floor(event)
        assert filtered == {}

    def test_returns_empty_for_missing_event_name(self) -> None:
        event: dict[str, object] = {"table_id": "uuid"}
        filtered = _filter_event_for_floor(event)
        assert filtered == {}


# ── FloorConsumer auth gate ──


@pytest.mark.django_db
def test_floor_consumer_rejects_unauthenticated() -> None:
    async def _test() -> None:
        communicator = WebsocketCommunicator(FloorConsumer.as_asgi(), "/ws/floor/")
        await communicator.connect()
        close_code = await communicator.receive_output(timeout=5)
        assert close_code["type"] == "websocket.close"
        assert close_code["code"] == 4001

    asyncio.run(_test())


@pytest.mark.django_db
def test_floor_consumer_allows_customer(restaurant: Any) -> None:
    async def _test() -> None:
        user = UserFactory.build(role=RoleCode.CUSTOMER)
        await sync_to_async(user.save)()
        access, _ = await sync_to_async(issue_tokens_with_restaurant)(user, restaurant.id)
        communicator = WebsocketCommunicator(
            application,
            "/ws/floor/",
            subprotocols=["access_token", access],
        )
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    asyncio.run(_test())


@pytest.mark.django_db
def test_floor_consumer_allows_waiter(restaurant: Any) -> None:
    async def _test() -> None:
        user = UserFactory.build(role=RoleCode.WAITER)
        await sync_to_async(user.save)()
        access, _ = await sync_to_async(issue_tokens_with_restaurant)(user, restaurant.id)
        communicator = WebsocketCommunicator(
            application,
            "/ws/floor/",
            subprotocols=["access_token", access],
        )
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    asyncio.run(_test())


# ── Staff emit functions send to correct group ──


@pytest.mark.django_db
def test_emit_cart_created_sends_to_staff_group(restaurant: Any) -> None:
    with patch("common.notification_events.get_channel_layer") as mock_get_layer:
        mock_layer = AsyncMock()
        mock_get_layer.return_value = mock_layer

        emit_cart_created(
            restaurant.id,
            session_id="test-session",
            table_number="T1",
            guest_name="Alice",
        )

        mock_layer.group_send.assert_called_once()
        call_args = mock_layer.group_send.call_args
        assert call_args[0][0] == staff_group_name(restaurant.id)
        event = call_args[0][1]["event"]
        assert event["type"] == "CART_CREATED"
        assert event["data"]["session_id"] == "test-session"
        assert event["data"]["table_number"] == "T1"
        assert event["data"]["guest_name"] == "Alice"


@pytest.mark.django_db
def test_emit_kitchen_ticket_injected_sends_to_staff_group(restaurant: Any) -> None:
    with patch("common.notification_events.get_channel_layer") as mock_get_layer:
        mock_layer = AsyncMock()
        mock_get_layer.return_value = mock_layer

        emit_kitchen_ticket_injected(
            restaurant.id,
            ticket_id="test-ticket",
            table_number="T1",
            items_count=3,
        )

        mock_layer.group_send.assert_called_once()
        call_args = mock_layer.group_send.call_args
        assert call_args[0][0] == staff_group_name(restaurant.id)
        event = call_args[0][1]["event"]
        assert event["type"] == "KITCHEN_TICKET_INJECTED"
        assert event["data"]["ticket_id"] == "test-ticket"
        assert event["data"]["items_count"] == 3


@pytest.mark.django_db
def test_emit_order_item_status_changed_sends_to_staff_group(restaurant: Any) -> None:
    with patch("common.notification_events.get_channel_layer") as mock_get_layer:
        mock_layer = AsyncMock()
        mock_get_layer.return_value = mock_layer

        emit_order_item_status_changed(
            restaurant.id,
            order_item_id="test-item",
            table_number="T1",
            menu_item_name="Burger",
            status="ready",
        )

        mock_layer.group_send.assert_called_once()
        call_args = mock_layer.group_send.call_args
        assert call_args[0][0] == staff_group_name(restaurant.id)
        event = call_args[0][1]["event"]
        assert event["type"] == "ORDER_ITEM_STATUS_CHANGED"
        assert event["data"]["order_item_id"] == "test-item"
        assert event["data"]["status"] == "ready"
        assert event["data"]["menu_item_name"] == "Burger"
