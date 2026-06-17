__all__ = [
    "add_item_to_cart",
    "create_cart_session",
    "create_order_with_items",
    "create_walk_in_reservation",
    "open_session",
    "remove_item_from_cart",
    "update_cart_item_quantity",
    "update_session_status",
    "void_order_item",
]


from datetime import timedelta
from decimal import Decimal
from typing import Final, cast

from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, transaction
from django.db.models import F, Max, Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.authentication.models import User
from apps.orders.broadcast import cart_group_send
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Table
from common.exceptions import (
    CartItemNotFoundError,
    CartSessionClosedError,
    MenuItemNotFoundError,
    MenuItemUnavailableError,
    ReservationConflictError,
    ReservationNotFoundError,
)
from common.hall_events import emit_hall_table_status_changed

from .models import (
    CartItem,
    CartSession,
    CartSessionStatus,
    Order,
    OrderItem,
    OrderItemStatus,
    OrderSource,
    OrderStatus,
    Session,
    SessionStatus,
    Ticket,
    TicketStatus,
    VoidReason,
)
from .selectors import (
    _resolve_allowed_reservation_participant_ids,
    get_cart_item,
    get_menu_item,
    get_reservation,
    is_cart_participant,
)


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
        existing = (
            CartSession.objects.select_for_update()
            .filter(reservation=reservation, status=CartSessionStatus.ACTIVE)
            .first()
        )
        if existing is not None:
            existing.participants.add(*allowed_participants)
            return existing
        try:
            with transaction.atomic():
                session = CartSession.objects.create(
                    restaurant_id=restaurant_id,
                    reservation=reservation,
                    created_by=user,
                )
        except IntegrityError:
            session = CartSession.objects.get(reservation=reservation, status=CartSessionStatus.ACTIVE)
        session.participants.add(*allowed_participants)
    return session


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


@transaction.atomic
def create_walk_in_reservation(
    *,
    table: Table,
    guest_count: int,
) -> Reservation:
    now = timezone.now()
    default_end = now + timedelta(hours=2)

    next_reservation = (
        Reservation.objects.filter(
            table=table,
            restaurant_id=table.restaurant_id,
            status__in=[ReservationStatus.PENDING, ReservationStatus.ACTIVE],
            end_at__gt=now,
        )
        .order_by("start_at")
        .first()
    )

    if next_reservation is not None:
        end_at = min(default_end, next_reservation.start_at)
    else:
        end_at = default_end

    if end_at <= now:
        raise ReservationConflictError("Table has no available time for a walk-in reservation.")

    return Reservation.objects.create(
        table=table,
        restaurant_id=table.restaurant_id,
        guest_count=guest_count,
        start_at=now,
        end_at=end_at,
        type=ReservationType.WALK_IN,
        status=ReservationStatus.ACTIVE,
        customer=None,
    )


@transaction.atomic
def update_session_status(
    session: Session,
    *,
    new_status: str,
    actor: User,
) -> Session:
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
    opened_at: object,
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
    items: list[dict],
    actor: User,
) -> Order:
    order = Order.objects.create(
        restaurant=session.restaurant,
        session=session,
        created_by=actor,
        created_by_source="staff",
        source=OrderSource.WAITER_MANUAL,
        status=OrderStatus.SUBMITTED,
        currency=session.currency,
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
            menu_item=menu_item,
            guest_slot=guest_slot,
            quantity=quantity,
            comment=comment,
            unit_price=unit_price,
            total_price=total_price,
        )

    order.total_amount = total
    order.save(update_fields=["total_amount"])

    Ticket.objects.create(
        restaurant=session.restaurant,
        session=session,
        order=order,
        status=TicketStatus.INCOMING,
        injected_at=timezone.now(),
    )

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
        OrderItem.objects.filter(order=order)
        .exclude(status=OrderItemStatus.VOIDED)
        .aggregate(total=Sum("total_price"))
    )["total"]
    order.total_amount = remaining if remaining is not None else Decimal(0)
    order.save(update_fields=["total_amount"])

    return order_item
