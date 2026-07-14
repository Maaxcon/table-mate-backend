from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.utils import timezone

import common.notification_store as notification_store_module
from apps.authentication.models import RoleCode
from apps.authentication.services import issue_tokens, issue_tokens_with_restaurant
from apps.editor.consumers import (
    FloorConsumer,
    NotificationStreamConsumer,
    _filter_event_for_floor,
)
from apps.orders.models import Session, SessionStatus
from apps.orders.services.cart import create_order_with_items
from apps.reservations.models import Reservation, ReservationStatus
from common.channels import staff_group_name
from common.notification_events import (
    emit_cart_created,
    emit_kitchen_ticket_injected,
    emit_order_item_status_changed,
)
from common.notification_store import get_notification_history, store_notification_event
from core.routing import application
from tests.conftest import RestaurantFactory, UserFactory


@pytest.fixture(autouse=True)
def _inmemory_channel_layer(settings: Any) -> None:
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }


@pytest.fixture(autouse=True)
def _locmem_cache(settings: Any) -> Iterator[None]:
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
    cache.clear()
    yield
    cache.clear()


# ── Notification history persistence ──


@pytest.mark.django_db
def test_store_notification_event_uses_cache_lock(restaurant: Any) -> None:
    event = {"type": "TEST_EVENT", "data": {"id": "lock-guard"}}
    lock_cm = MagicMock()
    lock_cm.__enter__.return_value = None
    lock_cm.__exit__.return_value = None
    lock_factory = MagicMock(return_value=lock_cm)

    with patch.object(cache, "lock", lock_factory, create=True):
        store_notification_event(restaurant.id, event)

    lock_factory.assert_called_once()
    lock_cm.__enter__.assert_called_once()
    lock_cm.__exit__.assert_called_once()

    history = get_notification_history(restaurant.id)
    assert len(history) == 1
    assert history[0]["type"] == "TEST_EVENT"


@pytest.mark.django_db
def test_store_notification_event_falls_back_when_lock_unavailable(
    restaurant: Any, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("ERROR", logger="common.notification_store")
    event = {"type": "TEST_EVENT", "data": {"id": "lock-fallback"}}
    lock_cm = MagicMock()
    lock_cm.__enter__.side_effect = TimeoutError("busy")
    lock_cm.__exit__.return_value = None

    with patch.object(cache, "lock", return_value=lock_cm, create=True):
        store_notification_event(restaurant.id, event)

    history = get_notification_history(restaurant.id)
    assert len(history) == 1
    assert history[0]["data"]["id"] == "lock-fallback"
    assert any("lock" in record.message for record in caplog.records)


@pytest.mark.django_db
def test_store_notification_event_truncates_large_payloads(restaurant: Any) -> None:
    long_text = "x" * (notification_store_module._MAX_FIELD_LENGTH + 100)
    event: dict[str, Any] = {
        "type": "TEST_EVENT",
        "data": {
            "comment": long_text,
            "items": [
                {"note": long_text, "index": idx} for idx in range(notification_store_module._MAX_LIST_LENGTH + 5)
            ],
        },
    }

    store_notification_event(restaurant.id, event)

    history = get_notification_history(restaurant.id)
    stored = history[0]

    assert stored["data"]["comment"].endswith("...")
    assert len(stored["data"]["comment"]) == notification_store_module._MAX_FIELD_LENGTH
    assert len(stored["data"]["items"]) == notification_store_module._MAX_LIST_LENGTH
    assert stored["data"]["items"][0]["note"].endswith("...")
    assert event["data"]["comment"] == long_text  # original payload untouched


@pytest.mark.django_db
def test_notification_consumer_buffers_live_events_during_replay(restaurant: Any) -> None:
    async def _test() -> None:
        user = UserFactory.build(role=RoleCode.WAITER)
        await sync_to_async(user.save)()
        access, _ = await sync_to_async(issue_tokens_with_restaurant)(user, restaurant.id, str(restaurant.public_id))

        historical = [
            {"type": "CART_CREATED", "data": {"id": "hist-1", "table_number": "T1"}},
            {"type": "CART_CHECKED_OUT", "data": {"id": "hist-2", "table_number": "T1"}},
        ]
        for event in historical:
            await sync_to_async(store_notification_event)(restaurant.id, event)

        communicator = WebsocketCommunicator(
            application,
            "/ws/staff/notifications/",
            subprotocols=["access_token", access],
        )

        channel_layer = get_channel_layer()
        assert channel_layer is not None

        original_send = NotificationStreamConsumer._send_cached_notifications

        async def slow_send(self: NotificationStreamConsumer, restaurant_pk: int) -> None:
            await asyncio.sleep(0.05)
            await original_send(self, restaurant_pk)

        live_event = {"type": "KITCHEN_TICKET_INJECTED", "data": {"id": "live-1", "table_number": "T1"}}

        with patch.object(NotificationStreamConsumer, "_send_cached_notifications", new=slow_send):
            connect_task = asyncio.create_task(communicator.connect())
            await asyncio.sleep(0.01)
            await channel_layer.group_send(
                staff_group_name(restaurant.id),
                {"type": "notification.event", "event": live_event},
            )

            connected, _ = await connect_task
            assert connected

            received = [await communicator.receive_json_from(timeout=3) for _ in range(3)]
            ids = [event["data"]["id"] for event in received]
            assert ids == ["hist-1", "hist-2", "live-1"]

            await communicator.disconnect()

    asyncio.run(_test())


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
        access, _ = await sync_to_async(issue_tokens_with_restaurant)(user, restaurant.id, str(restaurant.public_id))
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
def test_notification_consumer_missing_restaurant_claim() -> None:
    async def _test() -> None:
        user = UserFactory.build(role=RoleCode.WAITER)
        await sync_to_async(user.save)()
        access, _ = await sync_to_async(issue_tokens)(user)
        communicator = WebsocketCommunicator(
            application,
            "/ws/staff/notifications/",
            subprotocols=["access_token", access],
        )
        connected, _ = await communicator.connect()
        assert connected
        close_code = await communicator.receive_output(timeout=5)
        assert close_code["type"] == "websocket.close"
        assert close_code["code"] == 4001

    asyncio.run(_test())


@pytest.mark.django_db
def test_notification_consumer_allows_waiter(restaurant: Any) -> None:
    async def _test() -> None:
        user = UserFactory.build(role=RoleCode.WAITER)
        await sync_to_async(user.save)()
        access, _ = await sync_to_async(issue_tokens_with_restaurant)(user, restaurant.id, str(restaurant.public_id))
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
        access, _ = await sync_to_async(issue_tokens_with_restaurant)(user, restaurant.id, str(restaurant.public_id))
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
        access, _ = await sync_to_async(issue_tokens_with_restaurant)(user, restaurant.id, str(restaurant.public_id))
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
def test_notification_consumer_replays_cached_events(restaurant: Any) -> None:
    async def _test() -> None:
        user = UserFactory.build(role=RoleCode.WAITER)
        await sync_to_async(user.save)()
        access, _ = await sync_to_async(issue_tokens_with_restaurant)(user, restaurant.id, str(restaurant.public_id))

        historical = [
            {"type": "CART_CREATED", "data": {"id": "1", "table_number": "T1"}},
            {"type": "CART_CHECKED_OUT", "data": {"id": "2", "table_number": "T1"}},
        ]
        for event in historical:
            await sync_to_async(store_notification_event)(restaurant.id, event)

        communicator = WebsocketCommunicator(
            application,
            "/ws/staff/notifications/",
            subprotocols=["access_token", access],
        )
        connected, _ = await communicator.connect()
        assert connected

        first = await communicator.receive_json_from(timeout=3)
        assert first == historical[0]
        second = await communicator.receive_json_from(timeout=3)
        assert second == historical[1]

        await sync_to_async(emit_cart_created)(
            restaurant.id,
            session_id="session-live",
            table_number="T1",
            guest_name="Bob",
        )
        live = await communicator.receive_json_from(timeout=3)
        assert live["type"] == "CART_CREATED"

        await communicator.disconnect()

    asyncio.run(_test())


# ── Waiter order flow emits kitchen notification ──


@pytest.mark.django_db
def test_waiter_order_emits_kitchen_ticket_notification(
    restaurant: Any, table: Any, item: Any, restaurant_settings: Any
) -> None:
    waiter = UserFactory.build(role=RoleCode.WAITER, restaurant=restaurant)
    waiter.save()

    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        status=ReservationStatus.ACTIVE,
        start_at=timezone.now(),
        end_at=timezone.now() + timedelta(hours=2),
    )

    session = Session.objects.create(
        restaurant=restaurant,
        table=table,
        opened_by=waiter,
        guest_count=2,
        status=SessionStatus.OPEN,
        currency=restaurant_settings.currency,
        opened_at=timezone.now(),
        reservation=reservation,
    )

    def _run_immediately(func: Any, using: str | None = None) -> None:  # pragma: no cover - helper inside test
        func()

    with patch("django.db.transaction.on_commit", side_effect=_run_immediately):
        with patch("apps.orders.services.cart.emit_kitchen_ticket_injected") as mock_emit:
            create_order_with_items(
                session=session,
                items=[{"menu_item": item, "guest_slot": 1, "quantity": 1, "comment": None}],
                actor=waiter,
            )

            mock_emit.assert_called_once()
            call = mock_emit.call_args
            assert call.args[0] == restaurant.id
            assert call.kwargs["table_number"] == table.public_number
            assert call.kwargs["items_count"] == 1


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
        access, _ = await sync_to_async(issue_tokens_with_restaurant)(user, restaurant.id, str(restaurant.public_id))
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
        access, _ = await sync_to_async(issue_tokens_with_restaurant)(user, restaurant.id, str(restaurant.public_id))
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
    with (
        patch("common.notification_events.get_channel_layer") as mock_get_layer,
        patch("common.notification_events.store_notification_event") as mock_store,
    ):
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
        mock_store.assert_called_once_with(restaurant.id, ANY)


@pytest.mark.django_db
def test_emit_kitchen_ticket_injected_sends_to_staff_group(restaurant: Any) -> None:
    with (
        patch("common.notification_events.get_channel_layer") as mock_get_layer,
        patch("common.notification_events.store_notification_event") as mock_store,
    ):
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
        mock_store.assert_called_once_with(restaurant.id, ANY)


@pytest.mark.django_db
def test_emit_order_item_status_changed_sends_to_staff_group(restaurant: Any) -> None:
    with (
        patch("common.notification_events.get_channel_layer") as mock_get_layer,
        patch("common.notification_events.store_notification_event") as mock_store,
    ):
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
        mock_store.assert_called_once_with(restaurant.id, ANY)
