from __future__ import annotations

import json
import uuid
from typing import Any
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from apps.authentication.authentication import TokenVersionJWTAuthentication
from apps.authentication.models import User
from apps.orders.broadcast import cart_event_payload
from apps.orders.models import CartSession, CartSessionStatus
from apps.orders.selectors import is_cart_participant
from common.channels import cart_group_name


_TOKEN_SUBPROTOCOL = "access_token"


class CartConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    _accept_subprotocol: str | None = None

    async def connect(self) -> None:
        session_id = self.scope.get("url_route", {}).get("kwargs", {}).get("session_id")
        if not isinstance(session_id, uuid.UUID):
            await self.accept()
            await self.close(code=4003)
            return

        raw_token = self._extract_token()
        if raw_token is None:
            await self.accept()
            await self.close(code=4001)
            return

        jwt_auth = TokenVersionJWTAuthentication()
        try:
            validated_token = jwt_auth.get_validated_token(raw_token.encode())
        except TokenError:
            await self.accept()
            await self.close(code=4001)
            return

        payload = getattr(validated_token, "payload", {})
        if payload.get("is_guest"):
            if not await self._authorize_guest(payload, session_id):
                await self.accept()
                await self.close(code=4003)
                return
            self.scope["user"] = None
        else:
            user = await self._resolve_user(jwt_auth, validated_token)
            if user is None:
                await self.accept()
                await self.close(code=4001)
                return
            has_access = await self._user_has_access(session_id, user)
            if not has_access:
                await self.accept()
                await self.close(code=4003)
                return
            self.scope["user"] = user

        if self.channel_layer is None:
            await self.accept()
            await self.close(code=1011)
            return

        self.session_id = session_id
        self.group_name = cart_group_name(session_id)

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept(subprotocol=self._accept_subprotocol)
        await self._send_event("cart_updated")

    async def disconnect(self, code: int) -> None:
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        # Cart WebSocket is read-only; ignore any incoming messages.
        return

    async def cart_event(self, message: dict[str, Any]) -> None:
        await self.send(text_data=json.dumps(message["event"]))

    async def _send_event(self, event_type: str) -> None:
        payload = cart_event_payload(self.session_id, event_type)
        await self.send(text_data=json.dumps(payload))

    async def _authorize_guest(self, payload: dict[str, Any], session_id: uuid.UUID) -> bool:
        token_session = payload.get("cart_session_id")
        if token_session is None or str(token_session) != str(session_id):
            return False
        return bool(await self._session_is_active(session_id))

    def _extract_token(self) -> str | None:
        # Prefer the Sec-WebSocket-Protocol header so the token is never written
        # to access logs or browser history; fall back to the query string.
        subprotocols = self.scope.get("subprotocols") or []
        if len(subprotocols) >= 2 and subprotocols[0] == _TOKEN_SUBPROTOCOL:
            self._accept_subprotocol = _TOKEN_SUBPROTOCOL
            return subprotocols[1]

        raw_query_string = self.scope.get("query_string", b"")
        if isinstance(raw_query_string, bytes):
            query_string = raw_query_string.decode()
        else:
            query_string = str(raw_query_string)
        params: dict[str, list[str]] = parse_qs(query_string)
        tokens = params.get("token")
        if not tokens:
            return None
        return tokens[0]

    async def _resolve_user(self, jwt_auth: TokenVersionJWTAuthentication, validated_token: Any) -> User | None:
        try:
            user = await database_sync_to_async(jwt_auth.get_user)(validated_token)
        except (InvalidToken, AuthenticationFailed):
            return None
        if not isinstance(user, User):
            return None
        return user

    async def _session_is_active(self, session_id: uuid.UUID) -> bool:
        def _check() -> bool:
            return CartSession.objects.filter(public_id=session_id, status=CartSessionStatus.ACTIVE).exists()

        return bool(await database_sync_to_async(_check)())

    async def _user_has_access(self, session_id: uuid.UUID, user: User) -> bool:
        def _check() -> bool:
            session = (
                CartSession.objects.select_related("reservation")
                .prefetch_related("participants")
                .filter(public_id=session_id)
                .first()
            )
            if session is None or session.status != CartSessionStatus.ACTIVE:
                return False
            return is_cart_participant(user, session)

        return bool(await database_sync_to_async(_check)())


__all__ = ["CartConsumer"]
