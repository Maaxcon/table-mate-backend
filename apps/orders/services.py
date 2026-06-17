__all__ = [
    "add_item_to_cart",
    "checkout_cart_session",
    "close_stale_cart_sessions",
    "create_cart_session",
    "create_walk_in_reservation",
    "ensure_active_cart_for_table",
    "remove_item_from_cart",
    "update_cart_item_quantity",
]


from datetime import timedelta
from decimal import Decimal
from typing import Final, cast

from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, transaction
from django.db.models import F, Max, Q, Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.authentication.models import User
from apps.orders.broadcast import cart_group_send
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.reservations.selectors import get_active_reservation_for_table
from apps.restaurants.models import RestaurantSettings, Table
from common.exceptions import (
    CartItemNotFoundError,
    CartSessionClosedError,
    DomainError,
    EmptyCartError,
    MenuItemNotFoundError,
    MenuItemUnavailableError,
    NoActiveReservationError,
    ReservationConflictError,
    ReservationNotFoundError,
)

from .models import (
    CartItem,
    CartSession,
    CartSessionStatus,
    CreatedBySource,
    Order,
    OrderItem,
    OrderPaymentStatus,
    OrderSource,
    OrderStatus,
    Session,
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


def ensure_active_cart_for_table(
    *,
    table: Table,
    user: User | None = None,
) -> CartSession:
    """Return (or create) the active cart session for the table's active reservation.

    Finds the reservation in progress on the table. Raises NoActiveReservationError
    if there is none. Safe under concurrent scans: relies on the
    one_active_per_reservation unique constraint so two callers can never create
    two active sessions for the same reservation.
    """
    reservation = get_active_reservation_for_table(table)
    if reservation is None:
        raise NoActiveReservationError(f"Table {table.public_id} has no active reservation.")

    with transaction.atomic():
        existing = (
            CartSession.objects.select_for_update()
            .filter(reservation=reservation, status=CartSessionStatus.ACTIVE)
            .first()
        )
        if existing is not None:
            if user is not None:
                existing.participants.add(user)
            return existing
        try:
            with transaction.atomic():
                session = CartSession.objects.create(
                    restaurant_id=reservation.restaurant_id,
                    reservation=reservation,
                    created_by=user,
                )
        except IntegrityError:
            session = CartSession.objects.get(reservation=reservation, status=CartSessionStatus.ACTIVE)
        if user is not None:
            session.participants.add(user)
    return session


def _restaurant_billing(restaurant_id: int) -> tuple[str, Decimal]:
    settings = RestaurantSettings.objects.filter(restaurant_id=restaurant_id).first()
    if settings is None:
        return "USD", Decimal("0")
    return settings.currency or "USD", settings.default_tax_rate


def _get_or_create_visit_session(reservation: Reservation, *, currency: str, opened_by: User | None) -> Session:
    table_id = reservation.table_id
    if table_id is None:
        raise DomainError("Reservation has no table; cannot open a bill.")
    session, _ = Session.objects.get_or_create(
        reservation=reservation,
        defaults={
            "restaurant_id": reservation.restaurant_id,
            "table_id": table_id,
            "opened_by": opened_by,
            "guest_count": reservation.guest_count,
            "currency": currency,
            "opened_at": timezone.now(),
        },
    )
    return session


def _recompute_session_totals(session: Session) -> None:
    agg = Order.objects.filter(session=session).aggregate(
        total=Sum("total_amount"),
        tax=Sum("tax_total"),
    )
    total = agg["total"] or Decimal("0")
    tax = agg["tax"] or Decimal("0")
    session.total = total
    session.tax = tax
    session.subtotal = total - tax
    session.save(update_fields=["subtotal", "tax", "total"])


def checkout_cart_session(
    *,
    cart_session: CartSession,
    user: User | None = None,
) -> Order:
    """Fix the current cart round into an Order and close the cart.

    Creates (or reuses) the visit Session for the reservation, builds an Order
    with its items from the cart, closes the CartSession, then re-aggregates the
    Session totals across all its Orders. The Reservation stays active, so the
    next ensure_active_cart_for_table call opens a fresh cart for another round.
    """
    with transaction.atomic():
        cart_session = (
            CartSession.objects.select_for_update()
            .select_related("reservation")
            .get(pk=cart_session.pk)
        )
        if cart_session.status != CartSessionStatus.ACTIVE:
            raise CartSessionClosedError("Cart session is closed.")

        cart_items = list(CartItem.objects.filter(cart_session=cart_session).select_related("menu_item"))
        if not cart_items:
            raise EmptyCartError("Cart has no items to check out.")

        reservation = cart_session.reservation
        currency, tax_rate = _restaurant_billing(reservation.restaurant_id)
        session = _get_or_create_visit_session(reservation, currency=currency, opened_by=user)

        order = Order.objects.create(
            restaurant_id=cart_session.restaurant_id,
            session=session,
            created_by=user,
            created_by_source=CreatedBySource.CUSTOMER if user is not None else CreatedBySource.SYSTEM,
            source=OrderSource.CUSTOMER_PREPAID,
            status=OrderStatus.SUBMITTED,
            payment_status=OrderPaymentStatus.UNPAID,
            currency=currency,
        )

        order_subtotal = Decimal("0")
        order_tax = Decimal("0")
        for cart_item in cart_items:
            unit_price = cart_item.menu_item.price
            line_total = unit_price * cart_item.quantity
            line_tax = line_total * tax_rate
            OrderItem.objects.create(
                restaurant_id=cart_session.restaurant_id,
                order=order,
                menu_item=cart_item.menu_item,
                guest_slot=cart_item.guest_slot or 0,
                quantity=cart_item.quantity,
                comment=cart_item.comment,
                unit_price=unit_price,
                total_price=line_total,
                tax_rate=tax_rate,
                tax_amount=line_tax,
            )
            order_subtotal += line_total
            order_tax += line_tax

        order.tax_total = order_tax
        order.total_amount = order_subtotal + order_tax
        order.save(update_fields=["tax_total", "total_amount"])

        cart_session.status = CartSessionStatus.CLOSED
        cart_session.save(update_fields=["status"])

        _recompute_session_totals(session)
        _broadcast_cart_updated(cart_session)

    return order


def close_stale_cart_sessions() -> int:
    """Close active carts whose reservation is finished or past its end time.

    Keeps dead active CartSessions from piling up after a visit ends. Returns
    the number of carts closed. Time-valid active reservations are left alone.
    """
    now = timezone.now()
    stale = CartSession.objects.filter(status=CartSessionStatus.ACTIVE).filter(
        Q(reservation__status__in=[ReservationStatus.COMPLETED, ReservationStatus.CANCELLED])
        | Q(reservation__end_at__lt=now)
    )
    return stale.update(status=CartSessionStatus.CLOSED)


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
