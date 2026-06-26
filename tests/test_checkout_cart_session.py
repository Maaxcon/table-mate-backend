from collections.abc import Callable, Iterator
from datetime import timedelta
from decimal import Decimal
from typing import Any
from unittest import mock

import pytest
from django.utils import timezone

from apps.menu.models import MenuItem
from apps.orders.billing import checkout_cart_session
from apps.orders.models import (
    CartItem,
    CartSessionStatus,
    Order,
    OrderItem,
    OrderItemStatus,
    OrderPaymentStatus,
    OrderStatus,
    Session,
    SessionStatus,
)
from apps.orders.services import (
    add_item_to_cart,
    ensure_active_cart_for_table,
    pay_order_items,
    void_order_item,
)
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Restaurant, Table
from common.exceptions import (
    CartChangedError,
    CartSessionClosedError,
    DomainError,
    EmptyCartError,
    RestaurantClosedError,
)

UNIT_PRICE = Decimal("29.99")


@pytest.fixture(autouse=True)
def _restaurant_open() -> Iterator[None]:
    # The working-hours fixture is keyed on real wall-clock time, so every
    # checkout test would fail outside the configured hours. Pin the restaurant
    # open; the closed path has its own test that patches this to False.
    with (
        mock.patch("apps.orders.services.cart.is_restaurant_open", return_value=True),
        mock.patch("apps.orders.billing.is_restaurant_open", return_value=True),
    ):
        yield


def _active_reservation(restaurant: Restaurant, table: Table) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now - timedelta(minutes=30),
        end_at=now + timedelta(hours=1),
        status=ReservationStatus.ACTIVE,
        type=ReservationType.PRE_BOOKED,
    )


def _open_cart_with_item(table: Table, item: Any, quantity: int = 1) -> Any:
    cart = ensure_active_cart_for_table(table=table)
    add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=quantity)
    return cart


@pytest.mark.django_db
def test_checkout_creates_order_and_closes_cart(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    _active_reservation(restaurant, table)
    cart = _open_cart_with_item(table, item, quantity=2)

    order = checkout_cart_session(cart_session=cart)

    cart.refresh_from_db()
    assert cart.status == CartSessionStatus.CLOSED
    assert order.status == OrderStatus.SUBMITTED
    assert order.service_charge == Decimal("3.00")
    assert OrderItem.objects.filter(order=order).count() == 1

    session = Session.objects.get(reservation__table=table)
    assert order.session_id == session.id
    # 29.99 * 2 = 59.98 subtotal; 10% tax = 5.998 -> 6.00; 5% service = 2.999 -> 3.00
    assert session.subtotal == Decimal("59.98")
    assert session.tax == Decimal("6.00")
    assert session.service_charge == Decimal("3.00")
    assert session.total == Decimal("68.98")  # 59.98 + 6.00 + 3.00
    # Money is stored at the currency minor unit (no sub-cent residue).
    assert session.tax == session.tax.quantize(Decimal("0.01"))
    assert session.service_charge == session.service_charge.quantize(Decimal("0.01"))
    assert session.total == session.total.quantize(Decimal("0.01"))


@pytest.mark.django_db
def test_checkout_distributes_service_charge_so_bill_reconciles(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    _active_reservation(restaurant, table)
    cart = _open_cart_with_item(table, item, quantity=2)

    order = checkout_cart_session(cart_session=cart)

    items = list(OrderItem.objects.filter(order=order))
    # The single item absorbs the whole service charge, and what the guest pays
    # across the bill equals what the order owes.
    assert sum((i.service_charge_amount for i in items), Decimal("0")) == order.service_charge
    assert sum((i.payable for i in items), Decimal("0")) == order.total_amount


@pytest.mark.django_db
def test_service_charge_distribution_sums_exactly_across_items(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    _active_reservation(restaurant, table)
    cart = ensure_active_cart_for_table(table=table)
    # Prices chosen so the proportional shares have sub-cent parts that must be
    # rounded; the remainder has to land on the last item for the sum to be exact.
    for index, price in enumerate((Decimal("3.3300"), Decimal("3.3300"), Decimal("3.3400"))):
        menu_item = MenuItem.objects.create(
            restaurant=restaurant, menu=item.menu, name=f"Dish {index}", price=price
        )
        add_item_to_cart(session=cart, menu_item_id=str(menu_item.public_id), quantity=1)

    order = checkout_cart_session(cart_session=cart)
    items = list(OrderItem.objects.filter(order=order))

    assert len(items) == 3
    # Per-item shares sum exactly to the order service charge (no sub-cent drift)...
    assert sum((i.service_charge_amount for i in items), Decimal("0")) == order.service_charge
    # ...and the whole bill reconciles with the order total.
    assert sum((i.payable for i in items), Decimal("0")) == order.total_amount


@pytest.mark.django_db
def test_voiding_last_unpaid_item_marks_order_paid(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
    user_factory: Callable[..., Any],
) -> None:
    _active_reservation(restaurant, table)
    cart = ensure_active_cart_for_table(table=table)
    side = MenuItem.objects.create(restaurant=restaurant, menu=item.menu, name="Side", price=Decimal("5.0000"))
    add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=1)
    add_item_to_cart(session=cart, menu_item_id=str(side.public_id), quantity=1)
    order = checkout_cart_session(cart_session=cart)

    paid_item, unpaid_item = list(OrderItem.objects.filter(order=order).order_by("id"))
    next_cart = ensure_active_cart_for_table(table=table)
    pay_order_items(cart_session=next_cart, order_item_ids=[str(paid_item.public_id)])
    order.refresh_from_db()
    assert order.payment_status == OrderPaymentStatus.UNPAID

    actor = user_factory()
    actor.save()
    void_order_item(unpaid_item, actor=actor, void_reason_code="mispick")

    # Every remaining non-voided item is paid, so the order flips to PAID.
    order.refresh_from_db()
    assert order.payment_status == OrderPaymentStatus.PAID


@pytest.mark.django_db
def test_voiding_item_keeps_bill_reconciled(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
    user_factory: Callable[..., Any],
) -> None:
    _active_reservation(restaurant, table)
    cart = ensure_active_cart_for_table(table=table)
    side = MenuItem.objects.create(restaurant=restaurant, menu=item.menu, name="Side", price=Decimal("10.0000"))
    add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=1)
    add_item_to_cart(session=cart, menu_item_id=str(side.public_id), quantity=1)
    order = checkout_cart_session(cart_session=cart)

    to_void = OrderItem.objects.filter(order=order).order_by("id").first()
    assert to_void is not None
    actor = user_factory()
    actor.save()
    void_order_item(to_void, actor=actor, void_reason_code="mispick")

    order.refresh_from_db()
    remaining = list(OrderItem.objects.filter(order=order).exclude(status=OrderItemStatus.VOIDED))
    # total_amount still equals the surviving items' full payable (goods+tax+service)...
    assert order.total_amount == sum((i.payable for i in remaining), Decimal("0"))
    # ...and its tax/service parts reconcile, not left stale at pre-void values.
    subtotal = sum((i.total_price for i in remaining), Decimal("0"))
    assert order.total_amount == subtotal + order.tax_total + order.service_charge

    # The visit Session total reconciles too (service charge included).
    session = Session.objects.get(reservation__table=table)
    assert session.total == session.subtotal + session.tax + session.service_charge
    assert session.total == order.total_amount


@pytest.mark.django_db
def test_voiding_all_items_cancels_order_payment_status(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
    user_factory: Callable[..., Any],
) -> None:
    _active_reservation(restaurant, table)
    cart = _open_cart_with_item(table, item)
    order = checkout_cart_session(cart_session=cart)
    order_item = OrderItem.objects.get(order=order)

    actor = user_factory()
    actor.save()
    void_order_item(order_item, actor=actor, void_reason_code="mispick")

    # All items voided: nothing owed, nothing paid -> cancelled, not UNPAID.
    order.refresh_from_db()
    assert order.payment_status == OrderPaymentStatus.CANCELLED


@pytest.mark.django_db
def test_pay_rejected_on_closed_visit(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    _active_reservation(restaurant, table)
    cart = _open_cart_with_item(table, item)
    order = checkout_cart_session(cart_session=cart)
    order_item = OrderItem.objects.get(order=order)

    session = order.session
    session.status = SessionStatus.CLOSED
    session.save(update_fields=["status"])

    next_cart = ensure_active_cart_for_table(table=table)
    with pytest.raises(DomainError):
        pay_order_items(cart_session=next_cart, order_item_ids=[str(order_item.public_id)])

    order_item.refresh_from_db()
    assert order_item.is_paid is False


@pytest.mark.django_db
def test_two_rounds_accumulate_on_one_session(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    reservation = _active_reservation(restaurant, table)

    cart_one = _open_cart_with_item(table, item, quantity=1)
    checkout_cart_session(cart_session=cart_one)

    cart_two = _open_cart_with_item(table, item, quantity=1)
    assert cart_two.public_id != cart_one.public_id
    checkout_cart_session(cart_session=cart_two)

    sessions = Session.objects.filter(reservation=reservation)
    assert sessions.count() == 1
    session = sessions.get()
    assert Order.objects.filter(session=session).count() == 2
    # per round: 29.99 + tax 3.00 + service 1.50 = 34.49; two rounds = 68.98
    assert session.total == Decimal("68.98")
    assert session.service_charge == Decimal("3.00")


@pytest.mark.django_db
def test_reservation_stays_active_after_checkout(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    reservation = _active_reservation(restaurant, table)
    cart = _open_cart_with_item(table, item)

    checkout_cart_session(cart_session=cart)

    reservation.refresh_from_db()
    assert reservation.status == ReservationStatus.ACTIVE


@pytest.mark.django_db
def test_ensure_after_checkout_returns_new_cart(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    _active_reservation(restaurant, table)
    cart = _open_cart_with_item(table, item)
    checkout_cart_session(cart_session=cart)

    new_cart = ensure_active_cart_for_table(table=table)

    assert new_cart.status == CartSessionStatus.ACTIVE
    assert new_cart.public_id != cart.public_id


@pytest.mark.django_db
def test_checkout_empty_cart_raises(
    restaurant: Restaurant,
    table: Table,
    restaurant_settings: Any,
) -> None:
    _active_reservation(restaurant, table)
    cart = ensure_active_cart_for_table(table=table)

    with pytest.raises(EmptyCartError):
        checkout_cart_session(cart_session=cart)

    assert not Order.objects.exists()
    cart.refresh_from_db()
    assert cart.status == CartSessionStatus.ACTIVE


@pytest.mark.django_db
def test_checkout_closed_cart_raises(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    _active_reservation(restaurant, table)
    cart = _open_cart_with_item(table, item)
    checkout_cart_session(cart_session=cart)

    with pytest.raises(CartSessionClosedError):
        checkout_cart_session(cart_session=cart)

    assert Order.objects.count() == 1


@pytest.mark.django_db
def test_checkout_is_atomic_on_failure(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    _active_reservation(restaurant, table)
    cart = _open_cart_with_item(table, item)

    with mock.patch("apps.orders.billing.OrderItem.objects.create", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            checkout_cart_session(cart_session=cart)

    cart.refresh_from_db()
    assert cart.status == CartSessionStatus.ACTIVE
    assert not Order.objects.exists()
    assert not Session.objects.exists()


def _add_unavailable_item(cart: Any, item: Any) -> MenuItem:
    bad = MenuItem.objects.create(
        restaurant=item.restaurant,
        menu=item.menu,
        name="Soup",
        price=Decimal("10.0000"),
    )
    add_item_to_cart(session=cart, menu_item_id=str(bad.public_id), quantity=1)
    bad.is_available = False
    bad.save(update_fields=["is_available"])
    return bad


@pytest.mark.django_db
def test_checkout_prunes_unavailable_and_raises_changed(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    _active_reservation(restaurant, table)
    cart = ensure_active_cart_for_table(table=table)
    add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=1)
    bad = _add_unavailable_item(cart, item)

    with pytest.raises(CartChangedError) as exc:
        checkout_cart_session(cart_session=cart)

    assert [r["name"] for r in exc.value.removed] == ["Soup"]
    cart.refresh_from_db()
    assert cart.status == CartSessionStatus.ACTIVE
    assert not CartItem.objects.filter(cart_session=cart, menu_item=bad).exists()
    assert CartItem.objects.filter(cart_session=cart, menu_item=item).exists()
    assert not Order.objects.exists()


@pytest.mark.django_db
def test_checkout_after_prune_succeeds(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    _active_reservation(restaurant, table)
    cart = ensure_active_cart_for_table(table=table)
    add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=1)
    _add_unavailable_item(cart, item)

    with pytest.raises(CartChangedError):
        checkout_cart_session(cart_session=cart)
    order = checkout_cart_session(cart_session=cart)

    cart.refresh_from_db()
    assert cart.status == CartSessionStatus.CLOSED
    assert OrderItem.objects.filter(order=order).count() == 1


@pytest.mark.django_db
def test_checkout_sets_created_by_for_user(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
    user_factory: Callable[..., Any],
) -> None:
    user = user_factory()
    user.save()
    _active_reservation(restaurant, table)
    cart = _open_cart_with_item(table, item)

    order = checkout_cart_session(cart_session=cart, user=user)

    assert order.created_by_id == user.id


@pytest.mark.django_db
def test_checkout_blocked_when_restaurant_closed(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    _active_reservation(restaurant, table)
    cart = _open_cart_with_item(table, item)

    with mock.patch("apps.orders.billing.is_restaurant_open", return_value=False):
        with pytest.raises(RestaurantClosedError):
            checkout_cart_session(cart_session=cart)

    cart.refresh_from_db()
    assert cart.status == CartSessionStatus.ACTIVE
    assert not Order.objects.exists()
