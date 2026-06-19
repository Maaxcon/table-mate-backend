from collections.abc import Callable
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
    OrderStatus,
    Session,
)
from apps.orders.services import (
    add_item_to_cart,
    ensure_active_cart_for_table,
)
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Restaurant, Table
from common.exceptions import (
    CartChangedError,
    CartSessionClosedError,
    EmptyCartError,
    RestaurantClosedError,
)

UNIT_PRICE = Decimal("29.99")


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
    assert OrderItem.objects.filter(order=order).count() == 1

    session = Session.objects.get(reservation__table=table)
    assert order.session_id == session.id
    # 29.99 * 2 = 59.98 subtotal, 10% tax = 5.998 -> 6.00 (cents), total 65.98
    assert session.subtotal == Decimal("59.98")
    assert session.tax == Decimal("6.00")
    assert session.total == Decimal("65.98")
    # Money is stored at the currency minor unit (no sub-cent residue).
    assert session.tax == session.tax.quantize(Decimal("0.01"))
    assert session.total == session.total.quantize(Decimal("0.01"))


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
    # two rounds of 29.99 + 10% tax (2.999 -> 3.00) = 2 * 32.99 = 65.98
    assert session.total == Decimal("65.98")


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
