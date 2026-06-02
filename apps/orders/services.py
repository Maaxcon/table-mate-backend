__all__ = [
    "add_item_to_cart",
    "create_cart_session",
    "remove_item_from_cart",
]

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.authentication.models import User
from apps.reservations.models import Reservation
from apps.reservations.selectors import get_reservation_participant_ids
from common.exceptions import (
    CartItemNotFoundError,
    CartSessionClosedError,
    MenuItemNotFoundError,
    ReservationNotFoundError,
)

from .models import CartItem, CartSession, CartSessionStatus
from .selectors import get_cart_item, get_menu_item, get_reservation, is_cart_participant


def _resolve_allowed_reservation_participant_ids(reservation: Reservation) -> set[int]:
    participant_ids = set(get_reservation_participant_ids(reservation))
    if reservation.customer_id:
        participant_ids.add(reservation.customer_id)
    return participant_ids


def create_cart_session(
    *,
    restaurant_id: int,
    reservation_id: str,
    user: User,
) -> CartSession:
    reservation = get_reservation(restaurant_id, reservation_id)
    if reservation is None:
        raise ReservationNotFoundError(f"Reservation {reservation_id} not found.")

    allowed_participants = _resolve_allowed_reservation_participant_ids(reservation)
    if not allowed_participants or user.id not in allowed_participants:
        raise PermissionDenied("Only reservation participants may open a cart session.")

    with transaction.atomic():
        session = CartSession.objects.create(
            restaurant_id=restaurant_id,
            reservation=reservation,
            created_by=user,
        )
        session.participants.add(*allowed_participants)
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
        if session.status != CartSessionStatus.ACTIVE:
            raise CartSessionClosedError("Cart session is closed.")

        if not is_cart_participant(user, session):
            raise PermissionDenied("Only cart participants may add items.")

        menu_item = get_menu_item(session.restaurant_id, menu_item_id)
        if menu_item is None:
            raise MenuItemNotFoundError(f"Menu item {menu_item_id} not found.")

        try:
            with transaction.atomic():
                item, created = CartItem.objects.get_or_create(
                    cart_session=session,
                    menu_item=menu_item,
                    restaurant_id=session.restaurant_id,
                    defaults={"quantity": quantity, "added_by": user, "comment": comment},
                )
        except IntegrityError:
            item = (
                CartItem.objects.select_for_update()
                .filter(
                    cart_session=session,
                    menu_item=menu_item,
                    restaurant_id=session.restaurant_id,
                )
                .get()
            )
            created = False
        if not created:
            CartItem.objects.filter(pk=item.pk).update(
                quantity=F("quantity") + quantity,
                added_by=user,
                comment=comment,
                updated_at=timezone.now(),
            )
            item.refresh_from_db(fields=["quantity", "comment", "added_by_id", "updated_at"])

        item.menu_item = menu_item
        item.cart_session = session
        if "restaurant" in session.__dict__:
            item.restaurant = session.__dict__["restaurant"]
        item.added_by = user
    return item


def remove_item_from_cart(
    *,
    session: CartSession,
    item_id: str,
    user: User,
) -> None:
    with transaction.atomic():
        if session.status != CartSessionStatus.ACTIVE:
            raise CartSessionClosedError("Cart session is closed.")

        if not is_cart_participant(user, session):
            raise PermissionDenied("Only cart participants may remove items.")

        item = get_cart_item(session.restaurant_id, item_id, session)
        if item is None:
            raise CartItemNotFoundError(f"Cart item {item_id} not found.")

        item.delete()
