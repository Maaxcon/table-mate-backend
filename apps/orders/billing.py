__all__ = [
    "cancel_preorder",
    "checkout_cart_session",
    "close_reservation_carts",
    "close_visit_session",
    "confirm_and_pay_preorder",
    "ensure_preorder_session",
    "ensure_visit_session",
]


from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
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
    PreorderNotAllowedError,
    ReservationNotYetActiveError,
    RestaurantClosedError,
    TableOccupiedError,
    UnservedItemsError,
)
from common.hall_events import emit_hall_reservations_updated, emit_hall_table_status_changed
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


@contextmanager
def _table_occupied_on_conflict() -> Iterator[None]:
    """Translate orders_one_open_session_per_table into TableOccupiedError.

    That constraint firing means another reservation's visit is still open on
    this table (e.g. running over its slot). Surface a clear, specific error
    instead of a generic "conflicts" 409.
    """
    try:
        yield
    except IntegrityError as exc:
        if "orders_one_open_session_per_table" not in str(exc):
            raise
        raise TableOccupiedError(
            "This table's previous visit hasn't ended yet — try again shortly."
        ) from exc


def ensure_preorder_session(
    reservation: Reservation,
    *,
    opened_by: User | None = None,
    currency: str | None = None,
) -> Session:
    """Return (or create) the SCHEDULED Session holding a paid pre-order's bill.

    A pre-order is paid before the party arrives, but Order.session is required
    — so the bill has to exist now. It is created SCHEDULED rather than OPEN
    precisely so it does not occupy the table: every occupancy check (conflict
    detection, availability, orders_one_open_session_per_table, the cleanup
    jobs) filters on OPEN, so a booking weeks out no longer takes its table out
    of service for everyone else. ensure_visit_session promotes it when the
    party is actually seated.

    Repeat pre-order rounds reuse the same Session, as they did when this ran
    through ensure_visit_session.
    """
    table_id = reservation.table_id
    if table_id is None:
        raise DomainError("Reservation has no table; cannot open a bill.")
    if currency is None:
        currency, _, _ = _restaurant_billing(reservation.restaurant_id)

    existing = Session.objects.select_for_update().filter(reservation=reservation).first()
    if existing is not None:
        return existing

    return Session.objects.create(
        restaurant_id=reservation.restaurant_id,
        table_id=table_id,
        reservation=reservation,
        opened_by=opened_by,
        guest_count=reservation.guest_count,
        currency=currency,
        status=SessionStatus.SCHEDULED,
        opened_at=reservation.start_at,
        ends_at=reservation.end_at,
    )


def ensure_visit_session(
    reservation: Reservation,
    *,
    opened_by: User | None = None,
    currency: str | None = None,
) -> Session:
    """Return (or create) the OPEN visit Session (bill) for a reservation.

    One Session per reservation (OneToOne). Called when the table is actually
    opened — walk-in or pre-booked activation — so the floor plan shows the
    table as occupied consistently, and reused at checkout.

    A SCHEDULED session left behind by a paid pre-order is promoted to OPEN
    here, with opened_at moved to now: this call is the moment the party sits
    down and the table genuinely becomes occupied. Callers are all inside a
    transaction, so the select_for_update below serialises concurrent seatings
    of the same reservation.

    Promotion re-reads table and ends_at from the reservation. A SCHEDULED
    session can outlive several reschedules — reschedule_reservation and
    batch_update_reservations only rewrite the Session of an ACTIVE booking, so
    a pending one moved after its pre-order was paid leaves those two fields
    stale. Seating on the old table would occupy the wrong one, and a stale
    ends_at is already past, so close_overdue_visit_sessions would shut the
    visit on its next run.
    """
    table_id = reservation.table_id
    if table_id is None:
        raise DomainError("Reservation has no table; cannot open a bill.")
    if currency is None:
        currency, _, _ = _restaurant_billing(reservation.restaurant_id)

    existing = Session.objects.select_for_update().filter(reservation=reservation).first()
    if existing is not None:
        if existing.status == SessionStatus.SCHEDULED:
            existing.status = SessionStatus.OPEN
            existing.opened_at = timezone.now()
            existing.opened_by = opened_by
            existing.table_id = table_id
            existing.ends_at = reservation.end_at
            with _table_occupied_on_conflict():
                existing.save(
                    update_fields=[
                        "status",
                        "opened_at",
                        "opened_by",
                        "table",
                        "ends_at",
                        "updated_at",
                    ]
                )
        return existing

    with _table_occupied_on_conflict():
        session = Session.objects.create(
            restaurant_id=reservation.restaurant_id,
            table_id=table_id,
            reservation=reservation,
            opened_by=opened_by,
            guest_count=reservation.guest_count,
            currency=currency,
            opened_at=timezone.now(),
            ends_at=reservation.end_at,
        )
    return session


def close_reservation_carts(reservation: Reservation) -> list[CartSession]:
    """Close every ACTIVE CartSession for `reservation` and notify each guest
    cart that it has ended. Must run inside the caller's own
    transaction.atomic() (uses select_for_update) — the broadcast defers via
    _broadcast_cart_updated's own transaction.on_commit, so it's safe to call
    from here regardless of when the outer transaction actually commits.

    Without this, a guest whose reservation was cancelled/completed out from
    under them keeps a live cart: checkout_cart_session only checks the
    CartSession's own status, not the reservation's, so they could still
    order/checkout and inject a kitchen ticket against a booking staff
    already ended.
    """
    carts = list(
        CartSession.objects.select_for_update().filter(reservation=reservation, status=CartSessionStatus.ACTIVE)
    )
    for cart in carts:
        cart.status = CartSessionStatus.CLOSED
    if carts:
        CartSession.objects.bulk_update(carts, ["status"])
    for cart in carts:
        _broadcast_cart_updated(cart)
    return carts


def _finalize_session_orders_for_history(session: Session) -> None:
    """Mark non-cancelled session orders completed and snapshot receipts.

    Close-check in waiter flow is the moment the visit is finalized. We mirror
    that in persistence so cabinet history can immediately show the full check.
    Idempotent: completed orders and existing receipts are reused.
    """
    from apps.receipts.services import create_receipt_from_order

    orders = list(Order.objects.select_for_update().filter(session=session).exclude(status=OrderStatus.CANCELLED))
    if not orders:
        return

    stale_ids = {order.pk for order in orders if order.status != OrderStatus.COMPLETED}
    if stale_ids:
        Order.objects.filter(pk__in=stale_ids).update(status=OrderStatus.COMPLETED)
        for order in orders:
            if order.pk in stale_ids:
                order.status = OrderStatus.COMPLETED

    for order in orders:
        create_receipt_from_order(order)
def close_visit_session(*, session: Session, actor: User | None = None, force: bool = False) -> Session:
    """End a visit and free the table.

    Closes the Session (bill), marks the Reservation completed, closes any
    still-active CartSession, and sets the reservation end_at to now.
    Checks that all order items are served/voided before allowing close,
    unless `force` is set (used by the end-of-shift cleanup, which closes
    the table regardless so it doesn't stay wedged past closing).
    Idempotent — safe to call on an already-closed session.
    """
    with transaction.atomic():
        session = Session.objects.select_for_update().select_related("reservation").get(pk=session.pk)

        if session.status != SessionStatus.CLOSED:
            pending_count = OrderItem.objects.filter(
                order__session=session,
                status__in=[OrderItemStatus.PENDING, OrderItemStatus.IN_PROGRESS, OrderItemStatus.READY],
            ).count()
            if pending_count and not force:
                raise UnservedItemsError(
                    "Cannot close check: all items must be served or voided first.", count=pending_count
                )

            session.status = SessionStatus.CLOSED
            session.save(update_fields=["status"])

        _finalize_session_orders_for_history(session)

        reservation = session.reservation
        if reservation is not None:
            if reservation.status == ReservationStatus.ACTIVE:
                reservation.status = ReservationStatus.COMPLETED
                now = timezone.now()
                reservation.end_at = (
                    now if now > reservation.start_at else reservation.start_at + timedelta(seconds=1)
                )
                reservation.save(update_fields=["status", "end_at"])
            close_reservation_carts(reservation)

        table = session.table
        if actor is not None:
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
        transaction.on_commit(
            lambda: emit_hall_reservations_updated(session.restaurant_id, table_ids=[str(table.public_id)])
        )

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


def _build_order_from_cart(
    *,
    cart_session: CartSession,
    session: Session,
    user: User | None,
    currency: str,
    tax_rate: Decimal,
    service_charge_rate: Decimal,
    source: str = OrderSource.CUSTOMER_PREPAID,
) -> tuple[Order, list[OrderItem]]:
    """Turn a cart's items into an Order + OrderItems, closing the cart.

    Leaves OrderItem.ticket unset — callers attach a Ticket themselves, either
    immediately (checkout_cart_session) or later (confirm_and_pay_preorder,
    picked up by inject_scheduled_preorders near the reservation's start_at).
    """
    cart_items = list(CartItem.objects.filter(cart_session=cart_session).select_related("menu_item"))
    if not cart_items:
        raise EmptyCartError("Cart has no items to check out.")

    order = Order.objects.create(
        restaurant_id=cart_session.restaurant_id,
        session=session,
        created_by=user,
        created_by_source=CreatedBySource.CUSTOMER if user is not None else CreatedBySource.SYSTEM,
        source=source,
        status=OrderStatus.SUBMITTED,
        payment_status=OrderPaymentStatus.UNPAID,
        currency=currency,
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

    return order, order_items


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

        reservation = cart_session.reservation
        # Mirror of confirm_and_pay_preorder's PENDING guard, keeping the two
        # checkout endpoints disjoint. Without it a guest holding a pre-order
        # cart (create_cart_session does not gate on reservation status) could
        # POST to plain /checkout/ instead of /preorder-checkout/ and promote
        # their SCHEDULED session to OPEN weeks early — occupying the table and
        # firing the kitchen ticket immediately. Every legitimate in-visit cart
        # comes from ensure_active_cart_for_table, which already requires ACTIVE.
        if reservation.status != ReservationStatus.ACTIVE:
            raise ReservationNotYetActiveError(
                "This booking hasn't started yet — pre-order instead of checking out.",
                start_at=reservation.start_at.isoformat(),
            )

        currency, tax_rate, service_charge_rate = _restaurant_billing(reservation.restaurant_id)
        session = ensure_visit_session(reservation, opened_by=user, currency=currency)

        order, order_items = _build_order_from_cart(
            cart_session=cart_session,
            session=session,
            user=user,
            currency=currency,
            tax_rate=tax_rate,
            service_charge_rate=service_charge_rate,
        )

        ticket = Ticket.objects.create(
            restaurant=order.restaurant,
            session=session,
            order=order,
            status=TicketStatus.INCOMING,
            injected_at=timezone.now(),
        )
        OrderItem.objects.filter(pk__in=[item.pk for item in order_items]).update(ticket=ticket)

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
                items_count=len(order_items),
            )
        )

    # Broadcast after commit so websocket consumers don't read a pre-commit cart.
    _broadcast_cart_updated(cart_session)
    return order


def confirm_and_pay_preorder(
    *,
    cart_session: CartSession,
    user: User | None = None,
) -> Order:
    """Guest confirms and pays for a pre-order, ahead of their reservation's start_at.

    Builds the Order/OrderItems now, same as checkout, but leaves them without
    a Ticket — the kitchen doesn't see them until inject_scheduled_preorders
    creates one closer to arrival. Payment is the same simulated pattern used
    to split the bill (_pay_order_items_for_session in services/cart.py): no
    real money moves, items are simply marked paid.

    Only allowed while the reservation is still PENDING — once it's ACTIVE the
    guest just orders normally through checkout_cart_session.
    """
    removed = _prune_unavailable_cart_items(cart_session)
    if removed:
        raise CartChangedError(removed=removed)

    with transaction.atomic():
        cart_session = CartSession.objects.select_for_update().select_related("reservation").get(pk=cart_session.pk)
        if cart_session.status != CartSessionStatus.ACTIVE:
            raise CartSessionClosedError("Cart session is closed.")

        reservation = cart_session.reservation
        if reservation.status != ReservationStatus.PENDING:
            raise PreorderNotAllowedError()

        currency, tax_rate, service_charge_rate = _restaurant_billing(reservation.restaurant_id)
        session = ensure_preorder_session(reservation, opened_by=user, currency=currency)

        order, order_items = _build_order_from_cart(
            cart_session=cart_session,
            session=session,
            user=user,
            currency=currency,
            tax_rate=tax_rate,
            service_charge_rate=service_charge_rate,
            source=OrderSource.CUSTOMER_PREORDER,
        )

        OrderItem.objects.filter(pk__in=[item.pk for item in order_items]).update(is_paid=True)
        order.payment_status = OrderPaymentStatus.PAID
        order.save(update_fields=["payment_status"])

    _broadcast_cart_updated(cart_session)
    return order


def cancel_preorder(*, order: Order, user: User | None = None) -> Order:
    """Cancel a paid pre-order and simulate a refund, before the kitchen has it.

    Only allowed while no Ticket exists yet for the order — once
    inject_scheduled_preorders has picked it up, the kitchen is already
    working on it and it's too late to cancel from the guest side.
    """
    with transaction.atomic():
        order = Order.objects.select_for_update().select_related("session").get(pk=order.pk)
        if order.payment_status != OrderPaymentStatus.PAID:
            raise PreorderNotAllowedError("This pre-order isn't paid, so there's nothing to cancel.")
        if Ticket.objects.filter(order=order).exists():
            raise PreorderNotAllowedError(
                "The kitchen has already started this pre-order — it can't be cancelled."
            )

        OrderItem.objects.filter(order=order).update(status=OrderItemStatus.VOIDED, is_paid=False)
        order.status = OrderStatus.CANCELLED
        order.payment_status = OrderPaymentStatus.REFUNDED
        order.tax_total = Decimal("0")
        order.service_charge = Decimal("0")
        order.total_amount = Decimal("0")
        order.save(
            update_fields=["status", "payment_status", "tax_total", "service_charge", "total_amount"]
        )
        _recompute_session_totals(order.session)

    return order
