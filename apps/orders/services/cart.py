"""Cart-item operations: add, remove, update, and their shared helpers."""

__all__ = [
    "add_item_to_cart",
    "create_order_with_items",
    "emit_hall_table_status_changed",
    "get_bill_order_items",
    "open_session",
    "pay_order_items",
    "remove_item_from_cart",
    "update_cart_item_quantity",
    "update_session_status",
    "void_order_item",
]


from datetime import datetime
from decimal import Decimal
from typing import Any, Final, cast

from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, transaction
from django.db.models import F, Max, Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.authentication.models import User
from apps.orders.broadcast import cart_group_send
from apps.restaurants.models import Table
from apps.restaurants.selectors import is_restaurant_open
from common.exceptions import (
    CartItemNotFoundError,
    CartSessionClosedError,
    DomainError,
    MenuItemNotFoundError,
    MenuItemUnavailableError,
    ReservationConflictError,
    RestaurantClosedError,
)
from common.hall_events import emit_hall_table_status_changed

from ..models import (
    CartItem,
    CartSession,
    CartSessionStatus,
    Order,
    OrderItem,
    OrderItemStatus,
    OrderPaymentStatus,
    OrderSource,
    OrderStatus,
    Session,
    SessionStatus,
    Ticket,
    TicketStatus,
    VoidReason,
)
from ..selectors import (
    get_cart_item,
    get_menu_item,
    is_cart_participant,
)
from .walk_in import create_walk_in_reservation


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
            update_fields: dict[str, object] = {
                "quantity": F("quantity") + quantity,
                "updated_at": timezone.now(),
            }
            # The cart holds one row per menu item, so a re-add with a new comment
            # must overwrite the stored note. A blank/absent comment leaves the
            # existing one in place (e.g. tapping + on a card has no comment).
            if comment is not None:
                update_fields["comment"] = comment
            CartItem.objects.filter(pk=item.pk).update(**update_fields)
            item.refresh_from_db(fields=["quantity", "comment", "updated_at"])

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


def _visit_session_for_cart(cart_session: CartSession) -> Session | None:
    """The dining Session that holds this cart's orders (shared via reservation)."""
    if cart_session.reservation_id is None:
        return None
    return Session.objects.filter(reservation_id=cart_session.reservation_id).first()


def get_bill_order_items(*, cart_session: CartSession) -> list[OrderItem]:
    """Ordered (already-submitted) items for this table's visit — the bill.

    Pulls every non-voided OrderItem across the visit Session's orders, grouped
    later by ``guest_slot``. This is what the guest pays for, not the cart.
    """
    session = _visit_session_for_cart(cart_session)
    if session is None:
        return []
    return list(
        OrderItem.objects.filter(order__session=session)
        .exclude(status=OrderItemStatus.VOIDED)
        .select_related("menu_item")
        .order_by("guest_slot", "id")
    )


def _recompute_order_payment_status(order_ids: set[int]) -> None:
    for order_id in order_ids:
        items = OrderItem.objects.filter(order_id=order_id).exclude(status=OrderItemStatus.VOIDED)
        fully_paid = items.exists() and not items.filter(is_paid=False).exists()
        Order.objects.filter(pk=order_id).update(
            payment_status=OrderPaymentStatus.PAID if fully_paid else OrderPaymentStatus.UNPAID
        )


def pay_order_items(
    *,
    cart_session: CartSession,
    order_item_ids: list[str],
    client_id: str | None = None,
) -> list[OrderItem]:
    """Mark the given ordered items as paid (simulated — no money moves).

    Only non-voided, currently-unpaid items belonging to this table's visit are
    touched; unknown/already-paid ids are ignored (idempotent). An order flips to
    PAID once all its non-voided items are paid. Returns the full updated bill.
    """
    with transaction.atomic():
        session = _visit_session_for_cart(cart_session)
        if session is None:
            return []
        # A closed/voided visit is settled; paying against it would mutate a
        # finalised bill. The API can't reach this (it 401s on a closed cart),
        # but guard the service so any other caller fails loudly.
        if session.status != SessionStatus.OPEN:
            raise DomainError("Cannot pay items on a closed or voided visit.")

        to_pay = list(
            OrderItem.objects.select_for_update()
            .filter(order__session=session, public_id__in=order_item_ids, is_paid=False)
            .exclude(status=OrderItemStatus.VOIDED)
        )
        if to_pay:
            OrderItem.objects.filter(pk__in=[i.pk for i in to_pay]).update(
                is_paid=True,
                updated_at=timezone.now(),
            )
            _recompute_order_payment_status({i.order_id for i in to_pay})
            _broadcast_cart_updated(cart_session, client_id)

        return get_bill_order_items(cart_session=cart_session)


_SESSION_STATUS_TRANSITIONS: dict[str, set[str]] = {
    SessionStatus.OPEN: {SessionStatus.CLOSED, SessionStatus.VOIDED},
}


@transaction.atomic
def update_session_status(
    session: Session,
    *,
    new_status: str,
    actor: User,
) -> Session:
    if new_status not in SessionStatus.values:
        raise DomainError(f"Invalid session status: {new_status}.")

    if session.status in _SESSION_STATUS_TRANSITIONS:
        if new_status not in _SESSION_STATUS_TRANSITIONS[session.status]:
            raise ReservationConflictError(f"Cannot transition session from {session.status} to {new_status}.")
    elif new_status != session.status:
        raise ReservationConflictError(f"Cannot transition session from terminal state {session.status}.")

    previous_status = session.status
    session.status = new_status
    session.save(update_fields=["status", "updated_at"])

    if previous_status == SessionStatus.OPEN and new_status != SessionStatus.OPEN:
        table = session.table
        transaction.on_commit(
            lambda: emit_hall_table_status_changed(
                session.restaurant_id,
                table_id=str(table.public_id),
                previous_status="occupied",
                current_status="free",
                session_id=str(session.public_id),
                actor=actor,
            )
        )

    return session


@transaction.atomic
def open_session(
    *,
    restaurant_id: int,
    table: Table,
    guest_count: int,
    opened_by: User,
    currency: str,
    opened_at: str | datetime,
    actor: User,
) -> Session:
    from common.exceptions import TableOccupiedError

    if Session.objects.filter(table=table, status=SessionStatus.OPEN).exists():
        raise TableOccupiedError()

    reservation = create_walk_in_reservation(
        table=table,
        guest_count=guest_count,
    )

    session = Session.objects.create(
        restaurant_id=restaurant_id,
        table=table,
        reservation=reservation,
        opened_by=opened_by,
        guest_count=guest_count,
        status=SessionStatus.OPEN,
        currency=currency,
        opened_at=opened_at,
    )

    transaction.on_commit(
        lambda: emit_hall_table_status_changed(
            restaurant_id,
            table_id=str(table.public_id),
            previous_status="free",
            current_status="occupied",
            session_id=str(session.public_id),
            actor=actor,
        )
    )

    return session


@transaction.atomic
def create_order_with_items(
    *,
    session: Session,
    items: list[dict[str, Any]],
    actor: User,
) -> Order:
    if session.status != SessionStatus.OPEN:
        raise ReservationConflictError("Cannot add items to a session that is not open.")

    order = Order.objects.create(
        restaurant=session.restaurant,
        session=session,
        created_by=actor,
        created_by_source="staff",
        source=OrderSource.WAITER_MANUAL,
        status=OrderStatus.SUBMITTED,
        currency=session.currency,
    )

    ticket = Ticket.objects.create(
        restaurant=session.restaurant,
        session=session,
        order=order,
        status=TicketStatus.INCOMING,
        injected_at=timezone.now(),
    )

    total = 0
    for item_data in items:
        menu_item = item_data["menu_item"]
        guest_slot = item_data.get("guest_slot", 1)
        quantity = item_data.get("quantity", 1)
        comment = item_data.get("comment")
        unit_price = menu_item.price
        total_price = unit_price * quantity
        total += total_price

        OrderItem.objects.create(
            restaurant=session.restaurant,
            order=order,
            ticket=ticket,
            menu_item=menu_item,
            guest_slot=guest_slot,
            quantity=quantity,
            comment=comment,
            unit_price=unit_price,
            total_price=total_price,
        )

    order.total_amount = total
    order.save(update_fields=["total_amount"])

    agg = (
        OrderItem.objects.filter(
            order__session=session,
        )
        .exclude(
            status=OrderItemStatus.VOIDED,
        )
        .aggregate(
            subtotal=Sum("total_price"),
            tax=Sum("tax_amount"),
        )
    )

    session.subtotal = agg["subtotal"] or 0
    session.tax = agg["tax"] or 0
    session.total = session.subtotal + session.tax
    session.save(update_fields=["subtotal", "tax", "total"])

    return order


@transaction.atomic
def void_order_item(
    order_item: OrderItem,
    *,
    actor: User,
    void_reason_code: str,
    note: str | None = None,
) -> OrderItem:
    if order_item.status == OrderItemStatus.VOIDED:
        raise ValueError("Order item is already voided.")

    try:
        void_reason = VoidReason.objects.get(code=void_reason_code)
    except VoidReason.DoesNotExist:
        raise ValueError(f"Unknown void reason code: {void_reason_code}") from None

    order_item.status = OrderItemStatus.VOIDED
    order_item.voided_at = timezone.now()
    order_item.voided_by = actor
    order_item.void_reason = void_reason
    order_item.void_reason_note = note
    order_item.save(
        update_fields=[
            "status",
            "voided_at",
            "voided_by",
            "void_reason",
            "void_reason_note",
        ]
    )

    order = order_item.order
    remaining = (
        OrderItem.objects.filter(order=order).exclude(status=OrderItemStatus.VOIDED).aggregate(total=Sum("total_price"))
    )["total"]
    order.total_amount = remaining if remaining is not None else Decimal(0)
    order.save(update_fields=["total_amount"])

    _recompute_order_payment_status({order.id})

    session = order.session
    agg = (
        OrderItem.objects.filter(
            order__session=session,
        )
        .exclude(
            status=OrderItemStatus.VOIDED,
        )
        .aggregate(
            subtotal=Sum("total_price"),
            tax=Sum("tax_amount"),
        )
    )

    session.subtotal = agg["subtotal"] or 0
    session.tax = agg["tax"] or 0
    session.total = session.subtotal + session.tax
    session.save(update_fields=["subtotal", "tax", "total"])

    return order_item
