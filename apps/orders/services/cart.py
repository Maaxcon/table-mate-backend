"""Cart-item operations: add, remove, update, and their shared helpers."""

from typing import Final, cast

from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, transaction
from django.db.models import F, Max
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.authentication.models import User
from apps.orders.broadcast import cart_group_send
from apps.restaurants.selectors import is_restaurant_open
from common.exceptions import (
    CartItemNotFoundError,
    CartSessionClosedError,
    MenuItemNotFoundError,
    MenuItemUnavailableError,
    RestaurantClosedError,
)

from ..models import CartItem, CartSession, CartSessionStatus
from ..selectors import get_cart_item, get_menu_item, is_cart_participant


def _is_authenticated_user(user: User | AnonymousUser | None) -> bool:
    return user is not None and user.is_authenticated


def _broadcast_cart_updated(session: CartSession, client_id: str | None = None) -> None:
    session_id = session.public_id

    def _emit() -> None:
        cart_group_send(session_id, client_id=client_id)

    transaction.on_commit(_emit)


def _assign_guest_slot(session: CartSession, guest_identity: str) -> int:
    existing = (
        CartItem.objects.filter(cart_session=session, guest_identity=guest_identity)
        .exclude(guest_slot__isnull=True)
        .values_list("guest_slot", flat=True)
        .first()
    )
    if existing is not None:
        return existing
    highest = CartItem.objects.filter(cart_session=session).aggregate(highest=Max("guest_slot"))["highest"]
    return (highest or 0) + 1


def add_item_to_cart(
    *,
    session: CartSession,
    menu_item_id: str,
    quantity: int,
    user: User | AnonymousUser | None = None,
    guest_identity: str | None = None,
    guest_slot: int | None = None,
    comment: str | None = None,
    client_id: str | None = None,
) -> CartItem:
    with transaction.atomic():
        session = CartSession.objects.select_for_update().get(pk=session.pk)

        if session.status != CartSessionStatus.ACTIVE:
            raise CartSessionClosedError("Cart session is closed.")

        if not is_restaurant_open(session.restaurant_id):
            raise RestaurantClosedError()

        if _is_authenticated_user(user):
            user = cast(User, user)
            if not is_cart_participant(user, session):
                raise PermissionDenied("Only cart participants may add items.")
            session.participants.add(user)

        menu_item = get_menu_item(session.restaurant_id, menu_item_id, for_update=True)
        if menu_item is None:
            raise MenuItemNotFoundError(f"Menu item {menu_item_id} not found.")

        if not menu_item.is_available:
            raise MenuItemUnavailableError(f"Menu item '{menu_item.name}' is not available.")

        if guest_identity is not None:
            guest_slot = _assign_guest_slot(session, guest_identity)

        defaults: dict[str, object] = {
            "quantity": quantity,
            "comment": comment,
            "guest_slot": guest_slot,
            "guest_identity": guest_identity,
        }
        if _is_authenticated_user(user):
            user = cast(User, user)
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
            CartItem.objects.filter(pk=item.pk).update(
                quantity=F("quantity") + quantity,
                updated_at=timezone.now(),
            )
            item.refresh_from_db(fields=["quantity", "updated_at"])

        item.menu_item = menu_item
        item.cart_session = session
        if "restaurant" in session.__dict__:
            item.restaurant = session.__dict__["restaurant"]
        if _is_authenticated_user(user):
            user = cast(User, user)
            item.added_by = user
        _broadcast_cart_updated(session, client_id)
    return item


def remove_item_from_cart(
    *,
    session: CartSession,
    item_id: str,
    user: User | AnonymousUser | None = None,
    client_id: str | None = None,
) -> None:
    with transaction.atomic():
        session = CartSession.objects.select_for_update().get(pk=session.pk)

        if session.status != CartSessionStatus.ACTIVE:
            raise CartSessionClosedError("Cart session is closed.")

        if _is_authenticated_user(user):
            user = cast(User, user)
            if not is_cart_participant(user, session):
                raise PermissionDenied("Only cart participants may remove items.")
            session.participants.add(user)

        item = get_cart_item(session.restaurant_id, item_id, session)
        if item is None:
            raise CartItemNotFoundError(f"Cart item {item_id} not found.")

        item.delete()
        _broadcast_cart_updated(session, client_id)


class _UnsetType:
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return "<UNSET>"


_UNSET: Final = _UnsetType()


def update_cart_item_quantity(
    *,
    session: CartSession,
    item_id: str,
    quantity: int,
    user: User | AnonymousUser | None = None,
    comment: str | None | _UnsetType = _UNSET,
    guest_slot: int | None | _UnsetType = _UNSET,
    client_id: str | None = None,
) -> CartItem:
    with transaction.atomic():
        session = CartSession.objects.select_for_update().get(pk=session.pk)

        if session.status != CartSessionStatus.ACTIVE:
            raise CartSessionClosedError("Cart session is closed.")

        if _is_authenticated_user(user):
            user = cast(User, user)
            if not is_cart_participant(user, session):
                raise PermissionDenied("Only cart participants may update items.")
            session.participants.add(user)

        item = get_cart_item(session.restaurant_id, item_id, session)
        if item is None:
            raise CartItemNotFoundError(f"Cart item {item_id} not found.")

        locked_menu_item = get_menu_item(session.restaurant_id, str(item.menu_item.public_id), for_update=True)
        if locked_menu_item is None:
            raise MenuItemNotFoundError(f"Menu item {item.menu_item.public_id} not found.")
        item.menu_item = locked_menu_item

        if not item.menu_item.is_available:
            raise MenuItemUnavailableError(f"Menu item '{item.menu_item.name}' is not available.")

        changed = quantity != item.quantity
        if comment is not _UNSET and comment != item.comment:
            changed = True
        if guest_slot is not _UNSET and guest_slot != item.guest_slot:
            changed = True

        if not changed:
            return item

        update_fields: dict[str, object] = {
            "quantity": quantity,
            "updated_at": timezone.now(),
        }
        if comment is not _UNSET:
            update_fields["comment"] = comment
        if guest_slot is not _UNSET:
            update_fields["guest_slot"] = guest_slot
        CartItem.objects.filter(pk=item.pk).update(**update_fields)
        item.refresh_from_db()
        _broadcast_cart_updated(session, client_id)
        return item
