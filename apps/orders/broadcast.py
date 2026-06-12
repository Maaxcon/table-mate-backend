from __future__ import annotations

import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from common.channels import cart_group_name

_CART_EVENT_SCHEMA_VERSION = 1


def cart_event_payload(session_id: uuid.UUID, event_type: str = "cart_updated") -> dict[str, str | int]:
    return {
        "type": event_type,
        "session_id": str(session_id),
        "schema_version": _CART_EVENT_SCHEMA_VERSION,
    }


def cart_group_send(session_id: uuid.UUID, event_type: str = "cart_updated") -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    async_to_sync(channel_layer.group_send)(
        cart_group_name(session_id),
        {
            "type": "cart.event",
            "event": cart_event_payload(session_id, event_type),
        },
    )


__all__ = ["cart_event_payload", "cart_group_send"]
