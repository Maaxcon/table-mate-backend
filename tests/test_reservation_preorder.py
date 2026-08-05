from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.menu.models import MenuItem
from apps.orders.models import (
    Order,
    OrderItem,
    OrderItemStatus,
    OrderPaymentStatus,
    OrderSource,
    Session,
    SessionStatus,
    Ticket,
    TicketStatus,
)
from apps.reservations.models import Reservation, ReservationParticipant, ReservationStatus
from apps.restaurants.models import Restaurant, Table

from .conftest import AuthContext

pytestmark = pytest.mark.django_db


def _reservation(restaurant: Restaurant, table: Table, customer: Any) -> Reservation:
    now = timezone.now()
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        customer=customer,
        guest_count=2,
        start_at=now + timedelta(hours=2),
        end_at=now + timedelta(hours=4),
        status=ReservationStatus.PENDING,
    )


def _session(restaurant: Restaurant, table: Table, reservation: Reservation) -> Session:
    return Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        guest_count=reservation.guest_count,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=timezone.now(),
        ends_at=reservation.end_at,
    )


def _paid_round(
    restaurant: Restaurant,
    session: Session,
    item: MenuItem,
    *,
    quantity: int = 1,
    tax: Decimal = Decimal("10.00"),
    service_charge: Decimal = Decimal("5.00"),
) -> Order:
    goods = item.price * quantity
    order = Order.objects.create(
        restaurant=restaurant,
        session=session,
        currency="UAH",
        source=OrderSource.CUSTOMER_PREORDER,
        payment_status=OrderPaymentStatus.PAID,
        tax_total=tax,
        service_charge=service_charge,
        total_amount=goods + tax + service_charge,
    )
    OrderItem.objects.create(
        restaurant=restaurant,
        order=order,
        menu_item=item,
        guest_slot=1,
        quantity=quantity,
        status=OrderItemStatus.READY,
        unit_price=item.price,
        total_price=goods,
        is_paid=True,
    )
    return order


def _url(res: Reservation) -> str:
    return f"/api/reservations/reservations/{res.public_id}/preorder/"


def test_combines_multiple_paid_rounds_into_one_check(
    restaurant: Restaurant, table: Table, item: MenuItem, user_factory: Any, api: Any
) -> None:
    customer = user_factory()
    customer.save()
    reservation = _reservation(restaurant, table, customer)
    session = _session(restaurant, table, reservation)
    _paid_round(restaurant, session, item, quantity=1, tax=Decimal("10.00"), service_charge=Decimal("5.00"))
    _paid_round(restaurant, session, item, quantity=2, tax=Decimal("7.00"), service_charge=Decimal("3.00"))

    ctx: AuthContext = api(role=RoleCode.CUSTOMER)
    ctx.client.force_authenticate(user=customer)

    resp = ctx.client.get(_url(reservation))

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert len(data["items"]) == 2
    assert Decimal(data["tax"]) == Decimal("17.00")
    assert Decimal(data["service_charge"]) == Decimal("8.00")
    expected_total = (item.price * 1 + Decimal("10.00") + Decimal("5.00")) + (
        item.price * 2 + Decimal("7.00") + Decimal("3.00")
    )
    assert Decimal(data["total"]) == expected_total
    assert data["can_cancel"] is True


def test_excludes_cancelled_rounds(
    restaurant: Restaurant, table: Table, item: MenuItem, user_factory: Any, api: Any
) -> None:
    customer = user_factory()
    customer.save()
    reservation = _reservation(restaurant, table, customer)
    session = _session(restaurant, table, reservation)
    kept = _paid_round(restaurant, session, item)
    cancelled = _paid_round(restaurant, session, item)
    cancelled.payment_status = OrderPaymentStatus.REFUNDED
    cancelled.save(update_fields=["payment_status"])

    ctx: AuthContext = api(role=RoleCode.CUSTOMER)
    ctx.client.force_authenticate(user=customer)

    resp = ctx.client.get(_url(reservation))

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["order_id"] == str(kept.public_id)
    assert len(data["items"]) == 1


def test_returns_no_content_when_no_paid_rounds(
    restaurant: Restaurant, table: Table, user_factory: Any, api: Any
) -> None:
    customer = user_factory()
    customer.save()
    reservation = _reservation(restaurant, table, customer)
    _session(restaurant, table, reservation)

    ctx: AuthContext = api(role=RoleCode.CUSTOMER)
    ctx.client.force_authenticate(user=customer)

    resp = ctx.client.get(_url(reservation))

    assert resp.status_code == status.HTTP_204_NO_CONTENT


def test_cannot_cancel_once_any_round_has_a_ticket(
    restaurant: Restaurant, table: Table, item: MenuItem, user_factory: Any, api: Any
) -> None:
    customer = user_factory()
    customer.save()
    reservation = _reservation(restaurant, table, customer)
    session = _session(restaurant, table, reservation)
    _paid_round(restaurant, session, item)
    ticketed = _paid_round(restaurant, session, item)
    Ticket.objects.create(
        restaurant=restaurant,
        session=session,
        order=ticketed,
        status=TicketStatus.INCOMING,
        injected_at=timezone.now(),
    )

    ctx: AuthContext = api(role=RoleCode.CUSTOMER)
    ctx.client.force_authenticate(user=customer)

    resp = ctx.client.get(_url(reservation))

    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["can_cancel"] is False


def test_delete_cancels_every_paid_round(
    restaurant: Restaurant, table: Table, item: MenuItem, user_factory: Any, api: Any
) -> None:
    customer = user_factory()
    customer.save()
    reservation = _reservation(restaurant, table, customer)
    session = _session(restaurant, table, reservation)
    first = _paid_round(restaurant, session, item)
    second = _paid_round(restaurant, session, item)

    ctx: AuthContext = api(role=RoleCode.CUSTOMER)
    ctx.client.force_authenticate(user=customer)

    resp = ctx.client.delete(_url(reservation))

    assert resp.status_code == status.HTTP_204_NO_CONTENT
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.payment_status == OrderPaymentStatus.REFUNDED
    assert second.payment_status == OrderPaymentStatus.REFUNDED


def test_a_participant_can_see_the_preorder_they_helped_pay_for(
    restaurant: Restaurant, table: Table, item: MenuItem, user_factory: Any, api: Any
) -> None:
    # create_cart_session lets any participant open the cart and pay, so the
    # check has to be visible to them — it used to 404 for anyone but the owner.
    customer = user_factory()
    customer.save()
    friend = user_factory()
    friend.save()
    reservation = _reservation(restaurant, table, customer)
    ReservationParticipant.objects.create(reservation=reservation, user=friend)
    session = _session(restaurant, table, reservation)
    _paid_round(restaurant, session, item)

    ctx: AuthContext = api(role=RoleCode.CUSTOMER)
    ctx.client.force_authenticate(user=friend)

    resp = ctx.client.get(_url(reservation))

    assert resp.status_code == status.HTTP_200_OK
    assert len(resp.json()["items"]) == 1
    # Cancelling is all-or-nothing across the booking, so it stays with the
    # owner — and the flag says so, rather than offering a button that 403s.
    assert resp.json()["can_cancel"] is False


def test_a_participant_may_not_cancel_the_whole_bookings_preorder(
    restaurant: Restaurant, table: Table, item: MenuItem, user_factory: Any, api: Any
) -> None:
    customer = user_factory()
    customer.save()
    friend = user_factory()
    friend.save()
    reservation = _reservation(restaurant, table, customer)
    ReservationParticipant.objects.create(reservation=reservation, user=friend)
    session = _session(restaurant, table, reservation)
    order = _paid_round(restaurant, session, item)

    ctx: AuthContext = api(role=RoleCode.CUSTOMER)
    ctx.client.force_authenticate(user=friend)

    resp = ctx.client.delete(_url(reservation))

    assert resp.status_code == status.HTTP_403_FORBIDDEN
    order.refresh_from_db()
    assert order.payment_status == OrderPaymentStatus.PAID


def test_an_unrelated_customer_sees_nothing(
    restaurant: Restaurant, table: Table, item: MenuItem, user_factory: Any, api: Any
) -> None:
    customer = user_factory()
    customer.save()
    stranger = user_factory()
    stranger.save()
    reservation = _reservation(restaurant, table, customer)
    session = _session(restaurant, table, reservation)
    _paid_round(restaurant, session, item)

    ctx: AuthContext = api(role=RoleCode.CUSTOMER)
    ctx.client.force_authenticate(user=stranger)

    # 404, not 403 — a stranger shouldn't learn the booking exists.
    assert ctx.client.get(_url(reservation)).status_code == status.HTTP_404_NOT_FOUND
    assert ctx.client.delete(_url(reservation)).status_code == status.HTTP_404_NOT_FOUND
