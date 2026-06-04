from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from http import HTTPStatus
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.authentication.models import User
from apps.menu.models import MenuItem
from apps.restaurants.models import RestaurantSettings, Table
from common.exceptions import DomainError

from .models import (
    CreatedBySource,
    Order,
    OrderItem,
    OrderSource,
    OrderStatus,
    Session,
    SessionStatus,
    Ticket,
    TicketStatus,
)

_FOUR_PLACES = Decimal("0.0001")


class MenuItemUnavailableError(DomainError):
    default_detail = "One or more menu items are unavailable."
    default_code = "menu_item_unavailable"
    default_status_code = HTTPStatus.CONFLICT


class GuestSlotInvalidError(DomainError):
    default_detail = "Guest slot exceeds the session guest count."
    default_code = "guest_slot_invalid"
    default_status_code = HTTPStatus.BAD_REQUEST


class TableNotFoundError(DomainError):
    default_detail = "Table not found."
    default_code = "table_not_found"
    default_status_code = HTTPStatus.NOT_FOUND


def _find_or_create_session(
    *, restaurant_id: int, table: Table, guest_count: int, currency: str, user: User
) -> Session:
    now = timezone.now()
    session = (
        Session.objects.select_for_update()
        .filter(
            restaurant_id=restaurant_id,
            table=table,
            status=SessionStatus.OPEN,
        )
        .first()
    )
    if session is not None:
        return session

    return Session.objects.create(
        restaurant_id=restaurant_id,
        table=table,
        guest_count=guest_count,
        currency=currency,
        started_at=now,
        opened_by=user,
    )


def _compute_totals(
    *,
    items_data: list[dict[str, Any]],
    fetched_items: dict[str, MenuItem],
    tax_rate: Decimal,
) -> dict[str, Any]:
    total_amount = Decimal("0")
    tax_total = Decimal("0")
    order_items: list[dict[str, Any]] = []

    for entry in items_data:
        menu_item = fetched_items[str(entry["menu_item_id"])]
        qty = Decimal(str(entry["quantity"]))
        unit_price = menu_item.price
        line_total = (unit_price * qty).quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)
        line_tax = (line_total * tax_rate).quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)

        total_amount += line_total
        tax_total += line_tax

        order_items.append(
            {
                "menu_item": menu_item,
                "guest_slot": entry["guest_slot"],
                "quantity": entry["quantity"],
                "comment": entry.get("comment", ""),
                "unit_price": unit_price,
                "total_price": line_total,
                "tax_rate": tax_rate,
                "tax_amount": line_tax,
            }
        )

    total_amount = total_amount.quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)
    tax_total = tax_total.quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)

    return {
        "total_amount": total_amount,
        "tax_total": tax_total,
        "order_items_data": order_items,
    }


def submit_order(
    *,
    restaurant_id: int,
    table_id: str,
    items_data: list[dict[str, Any]],
    user: User,
    notes: str | None = None,
    idempotency_key: str | None = None,
) -> Order:
    menu_item_ids = [e["menu_item_id"] for e in items_data]
    max_guest_slot = max(e["guest_slot"] for e in items_data)
    guest_count = max(max_guest_slot + 1, 1)

    with transaction.atomic():
        table = Table.objects.select_for_update().filter(public_id=table_id, restaurant_id=restaurant_id).first()
        if table is None:
            raise TableNotFoundError()

        fetched_items: QuerySet[MenuItem] = MenuItem.objects.filter(
            public_id__in=menu_item_ids,
            restaurant_id=restaurant_id,
        ).select_for_update()

        fetched_map: dict[str, MenuItem] = {}
        for mi in fetched_items:
            fetched_map[str(mi.public_id)] = mi

        missing = [str(mid) for mid in menu_item_ids if str(mid) not in fetched_map]
        if missing:
            raise MenuItemUnavailableError(f"Menu items not found: {missing}")

        unavailable = [str(mi) for mi in fetched_map if not fetched_map[mi].is_available]
        if unavailable:
            raise MenuItemUnavailableError(f"Menu items unavailable: {unavailable}")

        settings = RestaurantSettings.objects.filter(restaurant_id=restaurant_id).first()
        currency = settings.currency if settings else "UAH"
        tax_rate = settings.default_tax_rate if settings else Decimal("0")

        session = _find_or_create_session(
            restaurant_id=restaurant_id,
            table=table,
            guest_count=guest_count,
            currency=currency,
            user=user,
        )

        for entry in items_data:
            if entry["guest_slot"] >= session.guest_count:
                raise GuestSlotInvalidError()

        totals = _compute_totals(
            items_data=items_data,
            fetched_items=fetched_map,
            tax_rate=tax_rate,
        )

        if idempotency_key:
            try:
                with transaction.atomic():
                    order = Order.objects.create(
                        restaurant_id=restaurant_id,
                        session=session,
                        created_by=user,
                        created_by_source=CreatedBySource.CUSTOMER,
                        source=OrderSource.CUSTOMER_PREPAID,
                        status=OrderStatus.SUBMITTED,
                        currency=currency,
                        total_amount=totals["total_amount"],
                        tax_total=totals["tax_total"],
                        notes=notes or "",
                        idempotency_key=idempotency_key,
                    )
            except IntegrityError:
                order = Order.objects.get(
                    session=session,
                    idempotency_key=idempotency_key,
                )
                return order
        else:
            order = Order.objects.create(
                restaurant_id=restaurant_id,
                session=session,
                created_by=user,
                created_by_source=CreatedBySource.CUSTOMER,
                source=OrderSource.CUSTOMER_PREPAID,
                status=OrderStatus.SUBMITTED,
                currency=currency,
                total_amount=totals["total_amount"],
                tax_total=totals["tax_total"],
                notes=notes or "",
            )

        ticket = Ticket.objects.create(
            restaurant_id=restaurant_id,
            session=session,
            order=order,
            status=TicketStatus.INCOMING,
            injected_at=datetime.now(UTC),
        )

        order_items: list[OrderItem] = []
        for item_data in totals["order_items_data"]:
            order_items.append(
                OrderItem(
                    restaurant_id=restaurant_id,
                    order=order,
                    ticket=ticket,
                    menu_item=item_data["menu_item"],
                    guest_slot=item_data["guest_slot"],
                    quantity=item_data["quantity"],
                    comment=item_data["comment"],
                    unit_price=item_data["unit_price"],
                    total_price=item_data["total_price"],
                    tax_rate=item_data["tax_rate"],
                    tax_amount=item_data["tax_amount"],
                )
            )
        OrderItem.objects.bulk_create(order_items)

    return order
