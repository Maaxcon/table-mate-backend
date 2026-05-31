from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from apps.authentication.models import RoleCode
from apps.menu.models import MenuItem
from apps.orders.models import Order, OrderItem, OrderPaymentStatus, OrderStatus, Session
from apps.payments.models import Payment
from apps.receipts.models import PaymentMethod, Receipt
from apps.receipts.services import create_receipt_from_order
from apps.reservations.models import Reservation
from apps.restaurants.models import Restaurant, Table


def _build_order(
    restaurant: Restaurant,
    table: Table,
    item: MenuItem,
    customer: Any,
    waiter: Any,
    *,
    status: str = OrderStatus.SUBMITTED,
    with_payment: bool = True,
) -> Order:
    now = timezone.now()
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        customer=customer,
        guest_count=2,
        start_at=now - timedelta(hours=2),
        end_at=now - timedelta(hours=1),
    )
    session = Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        opened_by=waiter,
        guest_count=2,
        currency="UAH",
        started_at=datetime(2026, 5, 18, 19, 30, tzinfo=UTC),
    )
    order = Order.objects.create(
        restaurant=restaurant,
        session=session,
        created_by=waiter,
        currency="UAH",
        tax_total=Decimal("4.2500"),
        service_charge=Decimal("4.2500"),
        tip_total=Decimal("6.0000"),
        status=status,
        payment_status=OrderPaymentStatus.PAID,
    )
    OrderItem.objects.create(
        restaurant=restaurant,
        order=order,
        menu_item=item,
        guest_slot=1,
        quantity=2,
        unit_price=Decimal("24.5000"),
    )
    if with_payment:
        Payment.objects.create(
            restaurant=restaurant,
            order=order,
            provider="cash",
            provider_transaction_id=f"tx-{order.id}",
            amount=Decimal("63.5000"),
            currency="UAH",
        )
    return order


@pytest.mark.django_db
def test_create_receipt_snapshot(
    restaurant: Restaurant,
    table: Table,
    item: MenuItem,
    user_factory: Callable[..., Any],
) -> None:
    customer = user_factory(role=RoleCode.CUSTOMER)
    customer.save()
    waiter = user_factory(role=RoleCode.WAITER, first_name="Olena", last_name="K")
    waiter.save()
    order = _build_order(restaurant, table, item, customer, waiter)

    receipt = create_receipt_from_order(order)

    assert receipt is not None
    assert receipt.customer_id == customer.pk
    assert receipt.order_id == order.pk
    assert receipt.payment is not None
    assert receipt.table_label == f"Table {table.table_number}"
    assert receipt.server_name == "Olena K"
    assert receipt.guests == 2
    assert receipt.payment_method == PaymentMethod.CASH
    assert receipt.payment_status == "Paid"
    # one item: 2 x 24.50 = 49.00 subtotal; +4.25 +4.25 +6.00 = 63.50 total
    assert receipt.items.count() == 1
    assert receipt.subtotal == Decimal("49.00")
    assert receipt.total == Decimal("63.50")


@pytest.mark.django_db
def test_create_receipt_is_idempotent(
    restaurant: Restaurant,
    table: Table,
    item: MenuItem,
    user_factory: Callable[..., Any],
) -> None:
    customer = user_factory(role=RoleCode.CUSTOMER)
    customer.save()
    waiter = user_factory(role=RoleCode.WAITER)
    waiter.save()
    order = _build_order(restaurant, table, item, customer, waiter)

    first = create_receipt_from_order(order)
    second = create_receipt_from_order(order)

    assert first is not None
    assert first.pk == second.pk
    assert Receipt.objects.filter(order=order).count() == 1


@pytest.mark.django_db
def test_signal_creates_receipt_on_completion(
    restaurant: Restaurant,
    table: Table,
    item: MenuItem,
    user_factory: Callable[..., Any],
) -> None:
    customer = user_factory(role=RoleCode.CUSTOMER)
    customer.save()
    waiter = user_factory(role=RoleCode.WAITER)
    waiter.save()
    order = _build_order(restaurant, table, item, customer, waiter, status=OrderStatus.SUBMITTED)
    assert not Receipt.objects.filter(order=order).exists()

    order.status = OrderStatus.COMPLETED
    order.save()

    assert Receipt.objects.filter(order=order).exists()


@pytest.mark.django_db
def test_no_receipt_without_customer(
    restaurant: Restaurant,
    table: Table,
    item: MenuItem,
    user_factory: Callable[..., Any],
) -> None:
    waiter = user_factory(role=RoleCode.WAITER)
    waiter.save()
    # Session/reservation without a customer, order created by a waiter.
    now = timezone.now()
    session = Session.objects.create(
        restaurant=restaurant,
        table=table,
        opened_by=waiter,
        guest_count=2,
        currency="UAH",
        started_at=now,
    )
    order = Order.objects.create(
        restaurant=restaurant,
        session=session,
        created_by=waiter,
        currency="UAH",
        status=OrderStatus.SUBMITTED,
    )

    assert create_receipt_from_order(order) is None
