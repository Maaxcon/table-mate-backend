from __future__ import annotations

import json

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.exceptions import ValidationError

from apps.authentication.models import RoleCode
from common.channels import (
    TOKEN_SUBPROTOCOL,
    authenticate_websocket,
    extract_ws_restaurant,
    extract_ws_token,
    hall_group_name,
    resolve_restaurant_pk,
    staff_group_name,
)

_HALL_ALLOWED_ROLES: frozenset[str] = frozenset({RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK})
_STAFF_ALLOWED_ROLES: frozenset[str] = frozenset({RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK})
_FLOOR_ALLOWED_ROLES: frozenset[str] = frozenset(
    {RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK, RoleCode.CUSTOMER}
)


class HallConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    async def connect(self) -> None:
        try:
            user, restaurant_id = await authenticate_websocket(self.scope)
        except Exception:
            await self.accept()
            await self.close(code=4001)
            return

        if user is None or restaurant_id is None:
            await self.accept()
            await self.close(code=4001)
            return

        if user.role not in _HALL_ALLOWED_ROLES:
            await self.accept()
            await self.close(code=4003)
            return

        self.group_name = hall_group_name(restaurant_id)

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def hall_event(self, message: dict[str, object]) -> None:
        await self.send(text_data=json.dumps(message["event"]))


class NotificationStreamConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    async def connect(self) -> None:
        try:
            user, restaurant_id = await authenticate_websocket(self.scope)
        except Exception:
            await self.accept()
            await self.close(code=4001)
            return

        if user is None or restaurant_id is None:
            await self.accept()
            await self.close(code=4001)
            return

        if user.role not in _STAFF_ALLOWED_ROLES:
            await self.accept()
            await self.close(code=4003)
            return

        self.group_name = staff_group_name(restaurant_id)

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        _, via_subprotocol = extract_ws_token(self.scope)
        subprotocol = TOKEN_SUBPROTOCOL if via_subprotocol else None
        await self.accept(subprotocol=subprotocol)

    async def disconnect(self, code: int) -> None:
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def hall_event(self, message: dict[str, object]) -> None:
        pass

    async def notification_event(self, message: dict[str, object]) -> None:
        await self.send(text_data=json.dumps(message["event"]))


_FLOOR_EVENT_FIELDS: dict[str, set[str]] = {
    "HALL_TABLE_STATUS_CHANGED": {"event_name", "table_id", "current_status", "occurred_at"},
    "HALL_NEW_RESERVATION": {"event_name", "table_id", "reservation_id", "start_at", "end_at", "occurred_at"},
    "HALL_RESERVATION_CANCELLED": {"event_name", "table_id", "reservation_id", "occurred_at"},
    "LAYOUT_PUBLISHED": {"event_name", "layout_version_public_id", "restaurant_public_id", "occurred_at"},
    "ZONE_CREATED": {"event_name", "zone_public_id", "zone_name", "occurred_at"},
    "ZONE_UPDATED": {"event_name", "zone_public_id", "zone_name", "occurred_at"},
    "ZONE_DELETED": {"event_name", "zone_public_id", "occurred_at"},
    "HALL_RESERVATIONS_UPDATED": {"event_name", "table_ids", "occurred_at"},
    "HALL_SESSION_AUTO_EXTENDED": {"event_name", "table_id", "ends_at", "clamped_by", "occurred_at"},
}


def _filter_event_for_floor(event: dict[str, object]) -> dict[str, object]:
    event_name = event.get("event_name", "")
    allowed = _FLOOR_EVENT_FIELDS.get(str(event_name), set())
    return {k: v for k, v in event.items() if k in allowed}


@sync_to_async
def _resolve_restaurant_from_uuid(public_id: str) -> int | None:
    from apps.restaurants.models import Restaurant

    try:
        return Restaurant.objects.values_list("id", flat=True).get(public_id=public_id)
    except (Restaurant.DoesNotExist, ValueError, ValidationError):
        return None


class StaffReservationsConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    """Admin/waiter WebSocket for reservation-specific hall events.

    Subscribes to the ``staff_{restaurant_id}`` group and forwards
    ``hall_event`` messages so admin clients receive reservation updates
    without sharing the waiter-oriented ``/ws/hall/`` channel.
    """

    async def connect(self) -> None:
        try:
            user, restaurant_id = await authenticate_websocket(self.scope)
        except Exception:
            await self.accept()
            await self.close(code=4001)
            return

        if user is None or restaurant_id is None:
            await self.accept()
            await self.close(code=4001)
            return

        if user.role not in _HALL_ALLOWED_ROLES:
            await self.accept()
            await self.close(code=4003)
            return

        self.group_name = staff_group_name(restaurant_id)

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def hall_event(self, message: dict[str, object]) -> None:
        await self.send(text_data=json.dumps(message["event"]))

    async def notification_event(self, message: dict[str, object]) -> None:
        # Staff reservation sockets share the same group as notification streams,
        # but they only surface hall-style payloads.
        pass


class FloorConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    async def connect(self) -> None:
        # Auth is optional here, not required: the floor stream is public — only
        # already-public table/reservation status leaks through (see
        # _filter_event_for_floor) — so an anonymous guest browsing the booking
        # page before logging in may still connect via ?restaurant=<public_id>,
        # same as the guest-facing floor page itself. A malformed/expired token
        # degrades to anonymous rather than rejecting the connection outright.
        try:
            user, restaurant_id = await authenticate_websocket(self.scope)
        except Exception:
            user, restaurant_id = None, None

        # An explicit ?restaurant=<public_id> wins over the token's restaurant
        # claim. Otherwise a staff member of one restaurant viewing another's
        # booking page would watch their *own* floor while the page shows
        # someone else's tables. Customers and anonymous guests carry no claim
        # and rely on the param entirely; fall back to the claim only when the
        # param is missing or unresolvable.
        public_id = extract_ws_restaurant(self.scope)
        if public_id:
            resolved = await resolve_restaurant_pk(public_id)
            if resolved is not None:
                restaurant_id = resolved

        if restaurant_id is None:
            await self.accept()
            await self.close(code=4001)
            return

        if user is not None and user.role not in _FLOOR_ALLOWED_ROLES:
            await self.accept()
            await self.close(code=4003)
            return

        self.group_name = hall_group_name(restaurant_id)

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def hall_event(self, message: dict[str, object]) -> None:
        event = message.get("event")
        if not isinstance(event, dict):
            return
        filtered = _filter_event_for_floor(event)
        await self.send(text_data=json.dumps(filtered))
