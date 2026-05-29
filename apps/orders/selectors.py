from apps.authentication.models import User
from apps.menu.models import MenuItem
from apps.reservations.models import Reservation

from .models import CartItem, CartSession


def is_cart_participant(user: User, session: CartSession) -> bool:
    return session.participants.filter(id=user.id).exists()


def get_cart_session(restaurant_id: int, session_pk: str) -> CartSession | None:
    return CartSession.objects.filter(public_id=session_pk, restaurant_id=restaurant_id).first()


def get_cart_item(restaurant_id: int, item_id: str, session: CartSession) -> CartItem | None:
    return CartItem.objects.filter(public_id=item_id, cart_session=session, restaurant_id=restaurant_id).first()


def get_reservation(restaurant_id: int, reservation_id: str) -> Reservation | None:
    return Reservation.objects.filter(public_id=reservation_id, restaurant_id=restaurant_id).first()


def get_menu_item(restaurant_id: int, menu_item_id: str) -> MenuItem | None:
    return MenuItem.objects.filter(public_id=menu_item_id, restaurant_id=restaurant_id).first()
