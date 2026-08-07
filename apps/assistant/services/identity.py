from __future__ import annotations

import uuid
from dataclasses import dataclass

from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.request import Request

from common.api import get_restaurant_id_from_auth


@dataclass(frozen=True)
class OwnerIdentity:
    """The acting guest: either an authenticated user or a JWT guest identity."""

    user: object | None = None
    guest_key: str = ""

    @property
    def is_guest(self) -> bool:
        return self.user is None and bool(self.guest_key)

    @property
    def rate_limit_key(self) -> str:
        if self.user is not None:
            return f"user:{getattr(self.user, 'pk', 'anon')}"
        return self.guest_key or "anon"

    def __post_init__(self) -> None:
        if bool(self.user) == bool(self.guest_key):
            raise ValueError("exactly one of user or guest_key must be set")


def guest_key_from_token(auth: object) -> str:
    payload = getattr(auth, "payload", {}) or {}
    guest_id = payload.get("guest_id")
    if guest_id:
        return f"guest:{guest_id}"
    cart_session_id = payload.get("cart_session_id")
    if cart_session_id:
        return f"guest:{cart_session_id}"
    return f"guest:{uuid.uuid4()}"


def owner_from_request(request: Request) -> OwnerIdentity:
    """Derive the acting guest identity from an authenticated request.

    Guest tokens (payload `is_guest`) map to a `guest:<id>` key; everything
    else is the authenticated user. The assistant never accepts anonymous
    requests.
    """
    auth = getattr(request, "auth", None)
    payload = getattr(auth, "payload", {}) if auth is not None else {}
    if isinstance(payload, dict) and payload.get("is_guest"):
        return OwnerIdentity(user=None, guest_key=guest_key_from_token(auth))

    user = getattr(request, "user", None)
    if user is None or getattr(user, "is_anonymous", True):
        raise AuthenticationFailed("Authentication required for the assistant.")
    return OwnerIdentity(user=user, guest_key="")


def require_restaurant_id(request: Request) -> int:
    """Restaurant scope for assistant requests; 403 when it cannot be derived.

    Staff tokens carry `restaurant_id`. Guest tokens do not, so the restaurant
    is resolved through the guest's cart session (every issued guest token is
    scoped to one `cart_session_id`).
    """
    restaurant_id = get_restaurant_id_from_auth(request)
    if restaurant_id is None:
        restaurant_id = _restaurant_from_guest_auth(request)
    if restaurant_id is None:
        raise PermissionDenied("No restaurant in the authentication context.")
    return restaurant_id


def _restaurant_from_guest_auth(request: Request) -> int | None:
    auth = getattr(request, "auth", None)
    payload = getattr(auth, "payload", {}) if auth is not None else {}
    cart_session_id = payload.get("cart_session_id") if isinstance(payload, dict) else None
    if not cart_session_id:
        return None
    from apps.orders.models import CartSession

    return CartSession.objects.filter(public_id=cart_session_id).values_list("restaurant_id", flat=True).first()


__all__ = ["OwnerIdentity", "guest_key_from_token", "owner_from_request", "require_restaurant_id"]
