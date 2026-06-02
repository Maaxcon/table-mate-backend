from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Order, OrderStatus


def _make_hall_event(event_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "schema_version": "1",
        "event_name": event_name,
        "occurred_at": datetime.now(UTC).isoformat(),
        **payload,
    }


@receiver(post_save, sender=Order, dispatch_uid="orders_broadcast_on_submit")
def broadcast_order_on_submit(sender: type[Order], instance: Order, **kwargs: Any) -> None:
    if instance.status != OrderStatus.SUBMITTED:
        return
    if not kwargs.get("created"):
        return

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    group_name = f"hall_{instance.restaurant_id}"
    event = _make_hall_event(
        "ORDER_SUBMITTED",
        {
            "order_id": str(instance.public_id),
            "restaurant_id": instance.restaurant_id,
            "session_id": str(instance.session.public_id),
            "status": instance.status,
            "total_amount": str(instance.total_amount),
            "currency": instance.currency,
        },
    )

    def _send() -> None:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {"type": "hall.event", "event": event},
        )

    transaction.on_commit(_send)
