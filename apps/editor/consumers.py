from __future__ import annotations

import json

from channels.generic.websocket import AsyncWebsocketConsumer

from apps.authentication.models import RoleCode
from common.channels import authenticate_websocket, hall_group_name

_HALL_ALLOWED_ROLES: frozenset[str] = frozenset({RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK})
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

    async def hall_event(self, message: dict) -> None:  # type: ignore[type-arg]
        await self.send(text_data=json.dumps(message["event"]))


_FLOOR_EVENT_FIELDS: dict[str, set[str]] = {
    "HALL_TABLE_STATUS_CHANGED": {"event_name", "table_id", "current_status", "occurred_at"},
    "HALL_NEW_RESERVATION": {"event_name", "table_id", "reservation_id", "start_at", "end_at", "occurred_at"},
    "HALL_RESERVATION_CANCELLED": {"event_name", "table_id", "occurred_at"},
}


def _filter_event_for_floor(event: dict[str, object]) -> dict[str, object]:
    event_name = event.get("event_name", "")
    allowed = _FLOOR_EVENT_FIELDS.get(str(event_name), set())
    return {k: v for k, v in event.items() if k in allowed}


class FloorConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
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

        if user.role not in _FLOOR_ALLOWED_ROLES:
            await self.accept()
            await self.close(code=4003)
            return

        self.group_name = hall_group_name(restaurant_id)

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def hall_event(self, message: dict) -> None:  # type: ignore[type-arg]
        filtered = _filter_event_for_floor(message["event"])
        await self.send(text_data=json.dumps(filtered))
