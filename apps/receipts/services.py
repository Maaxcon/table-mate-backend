from decimal import Decimal
from typing import cast

from django.db import transaction

from apps.authentication.models import RoleCode, User
from apps.orders.models import Order, OrderItemStatus, OrderPaymentStatus
from apps.payments.models import Payment
from common.money import quantize_money

from .models import PaymentMethod, Receipt, ReceiptItem


def _money(value: Decimal) -> Decimal:
    return quantize_money(value)


def _resolve_customer(order: Order) -> User | None:
    """The customer a receipt belongs to: the reservation guest, or the
    creator when they are a customer (e.g. a prepaid order).

    For staff-opened walk-ins there may be no guest account; in that case the
    waiter who opened the session owns the cabinet history snapshot.
    """
    session = order.session
    reservation = getattr(session, "reservation", None)
    if reservation is not None and reservation.customer_id:
        return cast(User, reservation.customer)
    creator = order.created_by
    if creator is not None and creator.role == RoleCode.CUSTOMER:
        return creator
    if session.opened_by_id:
        return cast(User, session.opened_by)
    return None


def _full_name(user: User | None) -> str:
    if user is None:
        return ""
    return f"{user.first_name} {user.last_name}".strip()


def _payment_for(order: Order) -> Payment | None:
    return order.payments.order_by("-created_at").first()


def _payment_method(payment: Payment | None) -> str:
    provider = payment.provider if payment is not None else ""
    return PaymentMethod.CASH if "cash" in provider.lower() else PaymentMethod.CARD


def _payment_status_label(order: Order) -> str:
    if order.payment_status in (OrderPaymentStatus.PAID, OrderPaymentStatus.SETTLED):
        return "Paid"
    return order.get_payment_status_display()


@transaction.atomic
def create_receipt_from_order(order: Order) -> Receipt | None:
    """Create an immutable cabinet receipt (a snapshot) from a finished order.

    Returns the existing receipt if one was already generated (idempotent),
    or None when the order has no customer to attribute it to.
    """
    customer = _resolve_customer(order)
    if customer is None:
        # No receipt can exist without a customer, so an unresolvable customer
        # also means there is nothing to return idempotently.
        return None

    session = order.session
    payment = _payment_for(order)

    # get_or_create closes the TOCTOU gap: if the same order reaches COMPLETED
    # twice concurrently, the order OneToOne constraint makes the losing insert
    # raise IntegrityError internally, which get_or_create swallows and re-reads
    # the winning row — no error-log noise and no duplicate items below.
    receipt, created = Receipt.objects.get_or_create(
        order=order,
        defaults={
            "customer": customer,
            "restaurant_id": order.restaurant_id,
            "payment": payment,
            "order_number": f"TM-{order.created_at:%Y%m%d}-{order.id}",
            "visited_at": session.opened_at or order.created_at,
            "currency": order.currency,
            "table_label": f"Table {session.table.public_number}" if session.table_id else "",
            "server_name": _full_name(session.opened_by),
            "guests": session.guest_count,
            "tax": _money(order.tax_total),
            "service_charge": _money(order.service_charge),
            "tip": _money(order.tip_total),
            "payment_method": _payment_method(payment),
            "payment_status": _payment_status_label(order),
        },
    )
    if not created:
        return receipt

    items = order.items.exclude(status=OrderItemStatus.VOIDED).exclude(is_wasted=True)
    for item in items.select_related("menu_item"):
        ReceiptItem.objects.create(
            receipt=receipt,
            menu_item=item.menu_item,
            name=item.menu_item.name,
            quantity=item.quantity,
            unit_price=_money(item.unit_price),
        )

    return receipt
