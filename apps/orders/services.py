from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from apps.authentication.models import User
from common.exceptions import CartItemNotFoundError, MenuItemNotFoundError, ReservationNotFoundError

from .models import CartItem, CartSession
from .selectors import get_cart_item, get_menu_item, get_reservation, is_cart_participant


def create_cart_session(
    *,
    restaurant_id: int,
    reservation_id: str,
    user: User,
) -> CartSession:
    reservation = get_reservation(restaurant_id, reservation_id)
    if reservation is None:
        raise ReservationNotFoundError(f"Reservation {reservation_id} not found.")

    with transaction.atomic():
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
    with transaction.atomic():
        if not is_cart_participant(user, session):
            raise PermissionDenied("Only cart participants may add items.")

        menu_item = get_menu_item(session.restaurant_id, menu_item_id)
        if menu_item is None:
            raise MenuItemNotFoundError(f"Menu item {menu_item_id} not found.")

        item = CartItem.objects.create(
            cart_session=session,
            menu_item=menu_item,
            quantity=quantity,
            added_by=user,
            comment=comment,
            restaurant_id=session.restaurant_id,
        )
    return item


def remove_item_from_cart(
    *,
    session: CartSession,
    item_id: str,
    user: User,
) -> None:
    with transaction.atomic():
        if not is_cart_participant(user, session):
            raise PermissionDenied("Only cart participants may remove items.")

        item = get_cart_item(session.restaurant_id, item_id, session)
        if item is None:
            raise CartItemNotFoundError(f"Cart item {item_id} not found.")

        item.delete()
