from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken, TokenError

from apps.authentication.authentication import TokenVersionJWTAuthentication

if TYPE_CHECKING:
    from apps.authentication.models import User


TOKEN_SUBPROTOCOL = "access_token"


def extract_ws_token(scope: dict) -> tuple[str | None, bool]:  # type: ignore[type-arg]
    """Pull the JWT from a WebSocket scope.

    Prefers the Sec-WebSocket-Protocol header (``["access_token", <jwt>]``) so the
    token stays out of URLs and access logs; falls back to the ``?token=`` query
    param. Returns ``(token, via_subprotocol)``.
    """
    subprotocols = scope.get("subprotocols") or []
    if len(subprotocols) >= 2 and subprotocols[0] == TOKEN_SUBPROTOCOL:
        return subprotocols[1], True

    raw_query_string = scope.get("query_string", b"")
    query_string = raw_query_string.decode() if isinstance(raw_query_string, bytes) else str(raw_query_string)
    tokens = parse_qs(query_string).get("token")
    if not tokens:
        return None, False
    return tokens[0], False


@database_sync_to_async  # type: ignore[untyped-decorator]
def _resolve_user(jwt_auth: TokenVersionJWTAuthentication, validated_token: object) -> User | None:
    try:
        return jwt_auth.get_user(validated_token)  # type: ignore[arg-type]
    except (InvalidToken, AuthenticationFailed):
        return None


async def authenticate_websocket(scope: dict) -> tuple[User | None, int | None]:  # type: ignore[type-arg]
    raw_token, _ = extract_ws_token(scope)
    if raw_token is None:
        return None, None

    jwt_auth = TokenVersionJWTAuthentication()
    try:
        validated_token = jwt_auth.get_validated_token(raw_token.encode())
    except TokenError:
        return None, None

    user = await _resolve_user(jwt_auth, validated_token)
    if user is None:
        return None, None

    claim = validated_token.get("restaurant_id")
    if claim is None:
        return None, None

    try:
        return user, int(claim)
    except (TypeError, ValueError):
        return None, None


def hall_group_name(restaurant_id: int) -> str:
    return f"hall_{restaurant_id}"


def cart_group_name(session_id: uuid.UUID) -> str:
    return f"cart_{session_id}"
