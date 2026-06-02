__all__ = [
    "get_cart_item",
    "get_cart_session",
    "get_menu_item",
    "get_reservation",
    "is_cart_participant",
]

from collections.abc import MutableMapping
from typing import cast

from apps.authentication.models import User
from apps.menu.models import MenuItem
from apps.reservations.models import Reservation

from .models import CartItem, CartSession


def is_cart_participant(user: User, session: CartSession) -> bool:
    cache = cast(MutableMapping[int, bool], session.__dict__.setdefault("_participant_cache", {}))

    user_id = user.id
    cached_value = cache.get(user_id)
    if cached_value is not None:
        return cached_value

    is_participant = session.participants.filter(id=user_id).exists()
    cache[user_id] = is_participant
    return is_participant


def get_cart_session(restaurant_id: int, session_pk: str) -> CartSession | None:
    return (
        CartSession.objects.select_related("restaurant")
        .filter(public_id=session_pk, restaurant_id=restaurant_id)
        .first()
    )


def get_cart_item(restaurant_id: int, item_id: str, session: CartSession) -> CartItem | None:
    return CartItem.objects.filter(public_id=item_id, cart_session=session, restaurant_id=restaurant_id).first()


def get_reservation(restaurant_id: int, reservation_id: str) -> Reservation | None:
    return Reservation.objects.filter(public_id=reservation_id, restaurant_id=restaurant_id).first()


def get_menu_item(restaurant_id: int, menu_item_id: str) -> MenuItem | None:
    return MenuItem.objects.filter(public_id=menu_item_id, restaurant_id=restaurant_id).first()
