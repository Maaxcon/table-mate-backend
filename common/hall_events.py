from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from .channels import hall_group_name

if TYPE_CHECKING:
    from apps.authentication.models import User

logger = logging.getLogger(__name__)


def _broadcast_hall_event(restaurant_id: int, event: dict[str, object]) -> None:
    channel_layer = get_channel_layer()
    try:
        async_to_sync(channel_layer.group_send)(
            hall_group_name(restaurant_id),
            {"type": "hall.event", "event": event},
        )
    except Exception:
        logger.exception(
            "Failed to broadcast hall event for restaurant %s", restaurant_id
        )


def emit_hall_table_status_changed(
    restaurant_id: int,
    *,
    table_id: str,
    previous_status: str,
    current_status: str,
    session_id: str,
    actor: User,
) -> None:
    _broadcast_hall_event(
        restaurant_id,
        {
            "event_name": "HALL_TABLE_STATUS_CHANGED",
            "schema_version": "1",
            "event_id": str(uuid.uuid4()),
            "table_id": table_id,
            "previous_status": previous_status,
            "current_status": current_status,
            "session_id": session_id,
            "actor_id": actor.pk,
            "actor_role": actor.role,
            "occurred_at": timezone.now().isoformat(),
        },
    )


def emit_hall_layout_published(
    restaurant_id: int,
    *,
    layout_version_id: int,
) -> None:
    _broadcast_hall_event(
        restaurant_id,
        {
            "event_name": "LAYOUT_PUBLISHED",
            "schema_version": "1",
            "event_id": str(uuid.uuid4()),
            "layout_version_id": layout_version_id,
            "restaurant_id": restaurant_id,
            "occurred_at": timezone.now().isoformat(),
        },
    )


def emit_hall_new_reservation(
    restaurant_id: int,
    *,
    reservation_id: str,
    table_id: str,
    start_at: str,
    end_at: str,
    actor: User,
) -> None:
    _broadcast_hall_event(
        restaurant_id,
        {
            "event_name": "HALL_NEW_RESERVATION",
            "schema_version": "1",
            "event_id": str(uuid.uuid4()),
            "reservation_id": reservation_id,
            "table_id": table_id,
            "start_at": start_at,
            "end_at": end_at,
            "actor_id": actor.pk,
            "actor_role": actor.role,
            "occurred_at": timezone.now().isoformat(),
        },
    )
