from __future__ import annotations

import logging
import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from common.channels import cart_group_name

logger = logging.getLogger(__name__)

_CART_EVENT_SCHEMA_VERSION = 2


def cart_event_payload(
    session_id: uuid.UUID,
    event_type: str = "cart_updated",
    client_id: str | None = None,
) -> dict[str, str | int]:
    payload: dict[str, str | int] = {
        "type": event_type,
        "session_id": str(session_id),
        "schema_version": _CART_EVENT_SCHEMA_VERSION,
    }
    if client_id is not None:
        payload["client_id"] = client_id
    return payload


def cart_group_send(
    session_id: uuid.UUID,
    event_type: str = "cart_updated",
    client_id: str | None = None,
) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    try:
        async_to_sync(channel_layer.group_send)(
            cart_group_name(session_id),
            {
                "type": "cart.event",
                "event": cart_event_payload(session_id, event_type, client_id),
            },
        )
    except Exception:
        logger.exception("Failed to broadcast cart event for session %s", session_id)


__all__ = ["cart_event_payload", "cart_group_send"]
