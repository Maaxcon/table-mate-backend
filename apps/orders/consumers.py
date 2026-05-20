from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from common.channels import authenticate_websocket, cart_group_name

from .models import Session


def _make_cart_event(event_name: str, payload: dict) -> dict:  # type: ignore[type-arg]
    return {
        "event_id": str(uuid.uuid4()),
        "schema_version": "1",
        "event_name": event_name,
        "occurred_at": datetime.now(UTC).isoformat(),
        **payload,
    }


class CartConsumer(AsyncWebsocketConsumer):
    async def connect(self) -> None:
        session_id: uuid.UUID = self.scope["url_route"]["kwargs"]["session_id"]

        user, restaurant_id = await authenticate_websocket(self.scope)
        if user is None or restaurant_id is None:
            await self.accept()
            await self.close(code=4001)
            return

        session = await _fetch_session(session_id, restaurant_id)
        if session is None:
            await self.accept()
            await self.close(code=4004)
            return

        self.session_id = session_id
        self.user = user
        self.group_name = cart_group_name(session_id)

        await self.channel_layer.group_add(self.group_name, self.channel_name)  # type: ignore[union-attr]
        await self.accept()

        await self.channel_layer.group_send(  # type: ignore[union-attr]
            self.group_name,
            {
                "type": "cart.event",
                "event": _make_cart_event(
                    "CART_PARTICIPANT_JOINED",
                    {
                        "session_id": str(self.session_id),
                        "user_id": str(self.user.public_id),
                    },
                ),
            },
        )

    async def disconnect(self, code: int) -> None:
        if not hasattr(self, "group_name"):
            return

        if hasattr(self, "user"):
            await self.channel_layer.group_send(  # type: ignore[union-attr]
                self.group_name,
                {
                    "type": "cart.event",
                    "event": _make_cart_event(
                        "CART_PARTICIPANT_LEFT",
                        {
                            "session_id": str(self.session_id),
                            "user_id": str(self.user.public_id),
                        },
                    ),
                },
            )

        await self.channel_layer.group_discard(self.group_name, self.channel_name)  # type: ignore[union-attr]

    async def cart_event(self, message: dict) -> None:  # type: ignore[type-arg]
        await self.send(text_data=json.dumps(message["event"]))


@database_sync_to_async
def _fetch_session(session_id: uuid.UUID, restaurant_id: int) -> Session | None:
    try:
        return Session.objects.get(public_id=session_id, restaurant_id=restaurant_id)
    except Session.DoesNotExist:
        return None
