from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError

if TYPE_CHECKING:
    from apps.authentication.models import User


@database_sync_to_async  # type: ignore[untyped-decorator]
def _resolve_user(jwt_auth: JWTAuthentication, validated_token: object) -> User | None:
    try:
        return cast("User", jwt_auth.get_user(validated_token))  # type: ignore[arg-type]
    except Exception:
        return None


async def authenticate_websocket(scope: dict) -> tuple[User | None, int | None]:  # type: ignore[type-arg]
    query_string = scope.get("query_string", b"").decode()
    params = parse_qs(query_string)
    token_list = params.get("token")
    if not token_list:
        return None, None

    jwt_auth = JWTAuthentication()
    try:
        validated_token = jwt_auth.get_validated_token(token_list[0].encode())
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


def cart_group_name(session_public_id: uuid.UUID | str) -> str:
    return f"cart_{str(session_public_id).replace('-', '')}"


def hall_group_name(restaurant_id: int) -> str:
    return f"hall_{restaurant_id}"
