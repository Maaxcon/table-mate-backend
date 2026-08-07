from __future__ import annotations

import json
import uuid
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from apps.authentication.authentication import TokenVersionJWTAuthentication
from apps.authentication.models import User
from common.channels import TOKEN_SUBPROTOCOL, extract_ws_token

from .models import Conversation
from .services.events import assistant_group_name
from .services.identity import guest_key_from_token


class AssistantConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    """Live feed for one conversation (C4): at-least-once event delivery.

    The socket is read-only from the guest's side; messages are sent via REST
    and the reply/proposal/result arrives here as an event.
    """

    _accept_subprotocol: str | None = None

    async def connect(self) -> None:
        conversation_id = self.scope.get("url_route", {}).get("kwargs", {}).get("conversation_id")
        if not isinstance(conversation_id, uuid.UUID):
            await self.accept()
            await self.close(code=4004)
            return

        raw_token = self._extract_token()
        if raw_token is None:
            await self.accept()
            await self.close(code=4001)
            return

        jwt_auth = TokenVersionJWTAuthentication()
        try:
            validated_token = jwt_auth.get_validated_token(raw_token.encode())
        except (InvalidToken, TokenError):
            await self.accept()
            await self.close(code=4001)
            return

        payload = getattr(validated_token, "payload", {})
        if payload.get("is_guest"):
            guest_key = guest_key_from_token(validated_token)
            if not await self._guest_owns_conversation(conversation_id, guest_key):
                await self.accept()
                await self.close(code=4003)
                return
            self.scope["guest_key"] = guest_key
            self.scope["user"] = None
        else:
            user = await self._resolve_user(jwt_auth, validated_token)
            if user is None or not await self._user_owns_conversation(conversation_id, user):
                await self.accept()
                await self.close(code=4003)
                return
            self.scope["user"] = user
            self.scope["guest_key"] = ""

        restaurant_id = payload.get("restaurant_id")
        if restaurant_id is not None and not await self._restaurant_matches(conversation_id, restaurant_id):
            await self.accept()
            await self.close(code=4003)
            return

        if self.channel_layer is None:
            await self.accept()
            await self.close(code=1011)
            return

        self.conversation_id = conversation_id
        self.group_name = assistant_group_name(conversation_id)

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept(subprotocol=self._accept_subprotocol)

    async def disconnect(self, code: int) -> None:
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        # Assistant socket is read-only; guest messages go through REST (202).
        return

    async def assistant_event(self, message: dict[str, Any]) -> None:
        await self.send(text_data=json.dumps(message["event"]))

    def _extract_token(self) -> str | None:
        token, via_subprotocol = extract_ws_token(self.scope)
        if via_subprotocol:
            self._accept_subprotocol = TOKEN_SUBPROTOCOL
        return token

    async def _resolve_user(self, jwt_auth: TokenVersionJWTAuthentication, validated_token: Any) -> User | None:
        try:
            user = await database_sync_to_async(jwt_auth.get_user)(validated_token)
        except (InvalidToken, AuthenticationFailed):
            return None
        if not isinstance(user, User):
            return None
        return user

    @database_sync_to_async
    def _guest_owns_conversation(self, conversation_id: uuid.UUID, guest_key: str) -> bool:
        return Conversation.objects.filter(
            public_id=conversation_id,
            guest_key=guest_key,
            user__isnull=True,
        ).exists()

    @database_sync_to_async
    def _user_owns_conversation(self, conversation_id: uuid.UUID, user: User) -> bool:
        return Conversation.objects.filter(
            public_id=conversation_id,
            user=user,
            guest_key="",
        ).exists()

    @database_sync_to_async
    def _restaurant_matches(self, conversation_id: uuid.UUID, restaurant_id: int) -> bool:
        return Conversation.objects.filter(
            public_id=conversation_id,
            restaurant_id=restaurant_id,
        ).exists()


__all__ = ["AssistantConsumer"]
