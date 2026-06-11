__all__ = [
    "add_item_to_cart",
    "create_cart_session",
    "remove_item_from_cart",
    "update_cart_item_quantity",
]


from django.contrib.auth.models import AnonymousUser
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
    MenuItemUnavailableError,
    ReservationNotFoundError,
)

from .models import CartItem, CartSession, CartSessionStatus
from .selectors import get_cart_item, get_menu_item, get_reservation, is_cart_participant


def _resolve_allowed_reservation_participant_ids(reservation: Reservation) -> set[int]:
    participant_ids = set(get_reservation_participant_ids(reservation))
    if reservation.customer_id:
        participant_ids.add(reservation.customer_id)
    return participant_ids


def _is_authenticated_user(user: User | AnonymousUser | None) -> bool:
    return user is not None and user.is_authenticated


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
    user: User | AnonymousUser | None = None,
    device_id: str | None = None,
    guest_slot: int | None = None,
    comment: str | None = None,
) -> CartItem:
    with transaction.atomic():
        session = CartSession.objects.select_for_update().get(pk=session.pk)

        if session.status != CartSessionStatus.ACTIVE:
            raise CartSessionClosedError("Cart session is closed.")

        if _is_authenticated_user(user):
            assert isinstance(user, User)
            if not is_cart_participant(user, session):
                raise PermissionDenied("Only cart participants may add items.")
            session.participants.add(user)

        menu_item = get_menu_item(session.restaurant_id, menu_item_id)
        if menu_item is None:
            raise MenuItemNotFoundError(f"Menu item {menu_item_id} not found.")

        if not menu_item.is_available:
            raise MenuItemUnavailableError(f"Menu item '{menu_item.name}' is not available.")

        defaults: dict[str, object] = {
            "quantity": quantity,
            "comment": comment,
            "guest_slot": guest_slot,
            "device_id": device_id,
        }
        if _is_authenticated_user(user):
            assert isinstance(user, User)
            defaults["added_by"] = user

        try:
            with transaction.atomic():
                item, created = CartItem.objects.get_or_create(
                    cart_session=session,
                    menu_item=menu_item,
                    restaurant_id=session.restaurant_id,
                    defaults=defaults,
                )
        except IntegrityError as exc:
            if exc.__cause__ is None or getattr(exc.__cause__, "pgcode", None) != "23505":
                raise
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
            update_fields = {
                "quantity": F("quantity") + quantity,
                "comment": comment,
                "guest_slot": guest_slot,
                "device_id": device_id,
                "updated_at": timezone.now(),
            }
            if _is_authenticated_user(user):
                assert isinstance(user, User)
                update_fields["added_by"] = user.id
            CartItem.objects.filter(pk=item.pk).update(**update_fields)
            item.refresh_from_db(fields=["quantity", "comment", "guest_slot", "device_id", "added_by_id", "updated_at"])

        item.menu_item = menu_item
        item.cart_session = session
        if "restaurant" in session.__dict__:
            item.restaurant = session.__dict__["restaurant"]
        if _is_authenticated_user(user):
            assert isinstance(user, User)
            item.added_by = user
    return item


def remove_item_from_cart(
    *,
    session: CartSession,
    item_id: str,
    user: User | AnonymousUser | None = None,
) -> None:
    with transaction.atomic():
        session = CartSession.objects.select_for_update().get(pk=session.pk)

        if session.status != CartSessionStatus.ACTIVE:
            raise CartSessionClosedError("Cart session is closed.")

        if _is_authenticated_user(user):
            assert isinstance(user, User)
            if not is_cart_participant(user, session):
                raise PermissionDenied("Only cart participants may remove items.")
            session.participants.add(user)

        item = get_cart_item(session.restaurant_id, item_id, session)
        if item is None:
            raise CartItemNotFoundError(f"Cart item {item_id} not found.")

        item.delete()


def update_cart_item_quantity(
    *,
    session: CartSession,
    item_id: str,
    quantity: int,
    user: User | AnonymousUser | None = None,
    comment: str | None = None,
    guest_slot: int | None = None,
) -> CartItem:
    with transaction.atomic():
        session = CartSession.objects.select_for_update().get(pk=session.pk)

        if session.status != CartSessionStatus.ACTIVE:
            raise CartSessionClosedError("Cart session is closed.")

        if _is_authenticated_user(user):
            assert isinstance(user, User)
            if not is_cart_participant(user, session):
                raise PermissionDenied("Only cart participants may update items.")
            session.participants.add(user)

        item = get_cart_item(session.restaurant_id, item_id, session)
        if item is None:
            raise CartItemNotFoundError(f"Cart item {item_id} not found.")

        if not item.menu_item.is_available:
            raise MenuItemUnavailableError(f"Menu item '{item.menu_item.name}' is not available.")

        update_fields: dict[str, object] = {
            "quantity": quantity,
            "comment": comment,
            "guest_slot": guest_slot,
            "updated_at": timezone.now(),
        }
        if _is_authenticated_user(user):
            assert isinstance(user, User)
            update_fields["added_by"] = user
        CartItem.objects.filter(pk=item.pk).update(**update_fields)
        item.refresh_from_db()
        return item
