from rest_framework.exceptions import PermissionDenied

from apps.authentication.models import User
from apps.menu.models import MenuItem
from apps.reservations.models import Reservation

from .models import CartItem, CartSession
from .selectors import is_cart_participant


def create_cart_session(
    *,
    restaurant_id: int,
    reservation_id: str,
    user: User,
) -> CartSession:
    reservation = Reservation.objects.get(
        public_id=reservation_id,
        restaurant_id=restaurant_id,
    )
    session = CartSession.objects.create(
        restaurant_id=restaurant_id,
        reservation=reservation,
        created_by=user,
    )
    session.participants.add(user)
    return session


def add_item_to_cart(
    *,
    session: CartSession,
    menu_item_id: str,
    quantity: int,
    user: User,
    comment: str | None = None,
) -> CartItem:
    if not is_cart_participant(user, session):
        raise PermissionDenied("Only cart participants may add items.")

    menu_item = MenuItem.objects.get(
        public_id=menu_item_id,
        restaurant_id=session.restaurant_id,
    )
    item = CartItem.objects.create(
        cart_session=session,
        menu_item=menu_item,
        quantity=quantity,
        added_by=user,
        comment=comment or "",
        restaurant_id=session.restaurant_id,
    )
    return item


def remove_item_from_cart(
    *,
    session: CartSession,
    item_id: str,
    user: User,
) -> None:
    if not is_cart_participant(user, session):
        raise PermissionDenied("Only cart participants may remove items.")

    item = CartItem.objects.get(
        public_id=item_id,
        cart_session=session,
        restaurant_id=session.restaurant_id,
    )
    item.delete()
