from __future__ import annotations

import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from .channels import staff_group_name


def _broadcast_staff_event(restaurant_id: int, event: dict[str, object]) -> None:
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        staff_group_name(restaurant_id),
        {"type": "notification.event", "event": event},
    )


def emit_cart_created(
    restaurant_id: int,
    *,
    session_id: str,
    table_number: str,
    guest_name: str | None = None,
) -> None:
    _broadcast_staff_event(
        restaurant_id,
        {
            "type": "CART_CREATED",
            "data": {
                "id": str(uuid.uuid4()),
                "session_id": session_id,
                "table_number": table_number,
                "guest_name": guest_name,
                "timestamp": timezone.now().isoformat(),
            },
        },
    )


def emit_cart_checked_out(
    restaurant_id: int,
    *,
    session_id: str,
    table_number: str,
    guest_name: str | None = None,
) -> None:
    _broadcast_staff_event(
        restaurant_id,
        {
            "type": "CART_CHECKED_OUT",
            "data": {
                "id": str(uuid.uuid4()),
                "session_id": session_id,
                "table_number": table_number,
                "guest_name": guest_name,
                "timestamp": timezone.now().isoformat(),
            },
        },
    )


def emit_hall_new_reservation_notification(
    restaurant_id: int,
    *,
    reservation_id: str,
    table_number: str,
    guest_name: str | None = None,
    guest_count: int = 0,
) -> None:
    _broadcast_staff_event(
        restaurant_id,
        {
            "type": "HALL_NEW_RESERVATION",
            "data": {
                "id": str(uuid.uuid4()),
                "reservation_id": reservation_id,
                "table_number": table_number,
                "guest_name": guest_name,
                "guest_count": guest_count,
                "timestamp": timezone.now().isoformat(),
            },
        },
    )


def emit_order_item_status_changed(
    restaurant_id: int,
    *,
    order_item_id: str,
    table_number: str,
    menu_item_name: str,
    status: str,
) -> None:
    _broadcast_staff_event(
        restaurant_id,
        {
            "type": "ORDER_ITEM_STATUS_CHANGED",
            "data": {
                "id": str(uuid.uuid4()),
                "order_item_id": order_item_id,
                "table_number": table_number,
                "menu_item_name": menu_item_name,
                "status": status,
                "timestamp": timezone.now().isoformat(),
            },
        },
    )


def emit_kitchen_ticket_injected(
    restaurant_id: int,
    *,
    ticket_id: str,
    table_number: str,
    items_count: int = 0,
) -> None:
    _broadcast_staff_event(
        restaurant_id,
        {
            "type": "KITCHEN_TICKET_INJECTED",
            "data": {
                "id": str(uuid.uuid4()),
                "ticket_id": ticket_id,
                "table_number": table_number,
                "items_count": items_count,
                "timestamp": timezone.now().isoformat(),
            },
        },
    )


def emit_cart_updated(
    session_id: str,
    *,
    client_id: str | None = None,
) -> None:
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"cart_{session_id}",
        {
            "type": "cart.updated",
            "payload": {
                "type": "cart_updated",
                "client_id": client_id,
            },
        },
    )
