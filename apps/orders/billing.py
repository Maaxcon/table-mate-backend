__all__ = [
    "checkout_cart_session",
    "ensure_visit_session",
]


from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.authentication.models import User
from apps.reservations.models import Reservation
from apps.restaurants.models import RestaurantSettings
from apps.restaurants.selectors import is_restaurant_open
from common.exceptions import (
    CartChangedError,
    CartSessionClosedError,
    DomainError,
    EmptyCartError,
    RestaurantClosedError,
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
from .services import _broadcast_cart_updated


def _restaurant_billing(restaurant_id: int) -> tuple[str, Decimal]:
    settings = RestaurantSettings.objects.filter(restaurant_id=restaurant_id).first()
    if settings is None:
        return "USD", Decimal("0")
    return settings.currency or "USD", settings.default_tax_rate


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
        currency, _ = _restaurant_billing(reservation.restaurant_id)
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
        cart_session = (
            CartSession.objects.select_for_update()
            .select_related("reservation")
            .get(pk=cart_session.pk)
        )
        if cart_session.status != CartSessionStatus.ACTIVE:
            raise CartSessionClosedError("Cart session is closed.")

        if not is_restaurant_open(cart_session.restaurant_id):
            raise RestaurantClosedError()

        cart_items = list(CartItem.objects.filter(cart_session=cart_session).select_related("menu_item"))
        if not cart_items:
            raise EmptyCartError("Cart has no items to check out.")

        reservation = cart_session.reservation
        currency, tax_rate = _restaurant_billing(reservation.restaurant_id)
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
