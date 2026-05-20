from __future__ import annotations

import json

from channels.generic.websocket import AsyncWebsocketConsumer

from apps.authentication.models import RoleCode
from common.channels import authenticate_websocket, hall_group_name

_HALL_ALLOWED_ROLES: frozenset[str] = frozenset(
    {RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK}
)


class HallConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    async def connect(self) -> None:
        user, restaurant_id = await authenticate_websocket(self.scope)
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
