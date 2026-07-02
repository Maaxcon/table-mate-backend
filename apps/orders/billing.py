__all__ = [
    "checkout_cart_session",
    "close_visit_session",
    "ensure_visit_session",
]


from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.authentication.models import User
from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import RestaurantSettings
from apps.restaurants.selectors import is_restaurant_open
from common.exceptions import (
    CartChangedError,
    CartSessionClosedError,
    DomainError,
    EmptyCartError,
    ReservationConflictError,
    RestaurantClosedError,
)
from common.hall_events import emit_hall_table_status_changed
from common.money import quantize_money
from common.notification_events import emit_cart_checked_out, emit_kitchen_ticket_injected

from .models import (
    CartItem,
    CartSession,
    CartSessionStatus,
    CreatedBySource,
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
)
from .services.cart import _broadcast_cart_updated


def _distribute_service_charge(
    order_items: list[OrderItem],
    order_subtotal: Decimal,
    order_service_charge: Decimal,
) -> None:
    """Spread the order-level service charge over its items, proportional to goods.

    Each item gets its rounded share; the last item absorbs the rounding remainder
    so the per-item shares sum exactly to ``order_service_charge`` (and the bill
    reconciles with ``Order.total_amount``). Persists ``service_charge_amount``.
    """
    if not order_items or order_service_charge <= 0 or order_subtotal <= 0:
        return
    allocated = Decimal("0")
    last_index = len(order_items) - 1
    for index, item in enumerate(order_items):
        if index == last_index:
            item.service_charge_amount = order_service_charge - allocated
        else:
            share = quantize_money(order_service_charge * item.total_price / order_subtotal)
            item.service_charge_amount = share
            allocated += share
    OrderItem.objects.bulk_update(order_items, ["service_charge_amount"])


def _restaurant_billing(restaurant_id: int) -> tuple[str, Decimal, Decimal]:
    settings = RestaurantSettings.objects.filter(restaurant_id=restaurant_id).first()
    if settings is None:
        return "USD", Decimal("0"), Decimal("0")
    return settings.currency or "USD", settings.default_tax_rate, settings.default_service_charge


def ensure_visit_session(
    reservation: Reservation,
    *,
    opened_by: User | None = None,
    currency: str | None = None,
) -> Session:
    """Return (or create) the visit Session (bill) for a reservation.

    One Session per reservation (OneToOne). Created eagerly when a table is
    opened — walk-in or pre-booked activation — so the floor plan shows the
    table as occupied consistently, and reused at checkout.
    """
    table_id = reservation.table_id
    if table_id is None:
        raise DomainError("Reservation has no table; cannot open a bill.")
    if currency is None:
        currency, _, _ = _restaurant_billing(reservation.restaurant_id)
    session, _ = Session.objects.get_or_create(
        reservation=reservation,
        defaults={
            "restaurant_id": reservation.restaurant_id,
            "table_id": table_id,
            "opened_by": opened_by,
            "guest_count": reservation.guest_count,
            "currency": currency,
            "opened_at": timezone.now(),
            "ends_at": reservation.end_at,
        },
    )
    return session


def close_visit_session(*, session: Session, actor: User | None = None) -> Session:
    """End a visit and free the table.

    Closes the Session (bill), marks the Reservation completed, closes any
    still-active CartSession, and sets the reservation end_at to now.
    Checks that all order items are served/voided before allowing close.
    Idempotent — safe to call on an already-closed session.
    """
    closed_carts: list[CartSession] = []
    with transaction.atomic():
        session = Session.objects.select_for_update().select_related("reservation").get(pk=session.pk)

        if session.status != SessionStatus.CLOSED:
            pending_items = OrderItem.objects.filter(
                order__session=session,
                status__in=[OrderItemStatus.PENDING, OrderItemStatus.IN_PROGRESS, OrderItemStatus.READY],
            ).exists()
            if pending_items:
                raise ReservationConflictError("Cannot close check: all items must be served or voided first.")

            session.status = SessionStatus.CLOSED
            session.save(update_fields=["status"])

        reservation = session.reservation
        if reservation is not None:
            if reservation.status == ReservationStatus.ACTIVE:
                reservation.status = ReservationStatus.COMPLETED
                reservation.end_at = timezone.now()
                reservation.save(update_fields=["status", "end_at"])
            closed_carts = list(
                CartSession.objects.select_for_update().filter(reservation=reservation, status=CartSessionStatus.ACTIVE)
            )
            for cart in closed_carts:
                cart.status = CartSessionStatus.CLOSED
            if closed_carts:
                CartSession.objects.bulk_update(closed_carts, ["status"])

        if actor is not None and session.table is not None:
            table = session.table
            sid = str(session.public_id)
            restaurant_id = session.restaurant_id
            transaction.on_commit(
                lambda: emit_hall_table_status_changed(
                    restaurant_id,
                    table_id=str(table.public_id),
                    previous_status="occupied",
                    current_status="free",
                    session_id=sid,
                    actor=actor,
                )
            )

    # Tell any open guest cart it has ended.
    for cart in closed_carts:
        _broadcast_cart_updated(cart)
    return session


def _recompute_session_totals(session: Session) -> None:
    agg = Order.objects.filter(session=session).aggregate(
        total=Sum("total_amount"),
        tax=Sum("tax_total"),
        service_charge=Sum("service_charge"),
    )
    total = agg["total"] or Decimal("0")
    tax = agg["tax"] or Decimal("0")
    service_charge = agg["service_charge"] or Decimal("0")
    session.total = total
    session.tax = tax
    session.service_charge = service_charge
    session.subtotal = total - tax - service_charge
    session.save(update_fields=["subtotal", "tax", "service_charge", "total"])


def _prune_unavailable_cart_items(cart_session: CartSession) -> list[dict[str, str]]:
    """Drop cart items whose menu item became unavailable. Returns what was removed.

    Committed on its own so the change survives the CART_CHANGED response and the
    next checkout call sees a clean cart.
    """
    with transaction.atomic():
        locked = CartSession.objects.select_for_update().get(pk=cart_session.pk)
        if locked.status != CartSessionStatus.ACTIVE:
            return []
        unavailable = list(
            CartItem.objects.filter(cart_session=locked, menu_item__is_available=False).select_related("menu_item")
        )
        if not unavailable:
            return []
        removed = [{"id": str(ci.menu_item.public_id), "name": ci.menu_item.name} for ci in unavailable]
        CartItem.objects.filter(pk__in=[ci.pk for ci in unavailable]).delete()
    _broadcast_cart_updated(cart_session)
    return removed


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

    Items whose menu item went unavailable are dropped first; if any were, the
    cart is left open and CartChangedError is raised so the guest can review the
    change and confirm again.
    """
    removed = _prune_unavailable_cart_items(cart_session)
    if removed:
        raise CartChangedError(removed=removed)

    with transaction.atomic():
        cart_session = CartSession.objects.select_for_update().select_related("reservation").get(pk=cart_session.pk)
        if cart_session.status != CartSessionStatus.ACTIVE:
            raise CartSessionClosedError("Cart session is closed.")

        if not is_restaurant_open(cart_session.restaurant_id):
            raise RestaurantClosedError()

        cart_items = list(CartItem.objects.filter(cart_session=cart_session).select_related("menu_item"))
        if not cart_items:
            raise EmptyCartError("Cart has no items to check out.")

        reservation = cart_session.reservation
        currency, tax_rate, service_charge_rate = _restaurant_billing(reservation.restaurant_id)
        session = ensure_visit_session(reservation, opened_by=user, currency=currency)

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

        ticket = Ticket.objects.create(
            restaurant=order.restaurant,
            session=session,
            order=order,
            status=TicketStatus.INCOMING,
            injected_at=timezone.now(),
        )

        order_items: list[OrderItem] = []
        order_subtotal = Decimal("0")
        order_tax = Decimal("0")
        # Build a map of guest_identity → display_name for this session.
        from apps.orders.models import GuestProfile
        guest_names = dict(
            GuestProfile.objects.filter(cart_session=cart_session).values_list("guest_identity", "display_name")
        )
        for cart_item in cart_items:
            unit_price = cart_item.menu_item.price
            line_total = quantize_money(unit_price * cart_item.quantity)
            line_tax = quantize_money(line_total * tax_rate)
            order_items.append(
                OrderItem.objects.create(
                    restaurant_id=cart_session.restaurant_id,
                    order=order,
                    ticket=ticket,
                    menu_item=cart_item.menu_item,
                    guest_slot=cart_item.guest_slot or 0,
                    guest_display_name=(
                        guest_names.get(cart_item.guest_identity) if cart_item.guest_identity else None
                    ),
                    quantity=cart_item.quantity,
                    comment=cart_item.comment,
                    unit_price=unit_price,
                    total_price=line_total,
                    tax_rate=tax_rate,
                    tax_amount=line_tax,
                )
            )
            order_subtotal += line_total
            order_tax += line_tax

        # Service charge applies to the goods subtotal and is not itself taxed.
        order_service_charge = quantize_money(order_subtotal * service_charge_rate)
        _distribute_service_charge(order_items, order_subtotal, order_service_charge)
        order.tax_total = order_tax
        order.service_charge = order_service_charge
        order.total_amount = order_subtotal + order_tax + order_service_charge
        order.save(update_fields=["tax_total", "service_charge", "total_amount"])

        cart_session.status = CartSessionStatus.CLOSED
        cart_session.save(update_fields=["status"])

        _recompute_session_totals(session)

        transaction.on_commit(
            lambda: emit_cart_checked_out(
                cart_session.restaurant_id,
                session_id=str(cart_session.public_id),
                table_number=session.table.public_number,
                guest_name=user.get_full_name() if user else None,
            )
        )
        transaction.on_commit(
            lambda: emit_kitchen_ticket_injected(
                cart_session.restaurant_id,
                ticket_id=str(ticket.public_id),
                table_number=session.table.public_number,
                items_count=len(cart_items),
            )
        )

    # Broadcast after commit so websocket consumers don't read a pre-commit cart.
    _broadcast_cart_updated(cart_session)
    return order
