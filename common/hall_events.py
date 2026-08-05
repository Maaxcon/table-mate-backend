from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.utils import timezone

from .channels import hall_group_name, staff_group_name

if TYPE_CHECKING:
    from apps.authentication.models import User
    from apps.reservations.models import Reservation

logger = logging.getLogger(__name__)

_DEDUP_NAMESPACE = uuid.UUID("a3f7b2c1-4d5e-6f78-9a0b-1c2d3e4f5a6b")
_DEDUP_TTL_SECONDS = 60


def _stable_event_id(event_name: str, *parts: str | int) -> str:
    """Derive a deterministic event_id from the event name and business keys."""
    key = f"{event_name}:{':'.join(str(p) for p in parts)}"
    return str(uuid.uuid5(_DEDUP_NAMESPACE, key))


def _broadcast_hall_event(restaurant_id: int, event: dict[str, object]) -> None:
    event_id = str(event.get("event_id", ""))
    # Only dedup events that carry an event_id. Events without one (e.g.
    # HALL_RESERVATIONS_UPDATED) would otherwise all collide on the empty key
    # "dedup:hall:" and every event after the first within the TTL would be dropped.
    if event_id:
        dedup_key = f"dedup:hall:{event_id}"
        if not cache.add(dedup_key, "1", timeout=_DEDUP_TTL_SECONDS):
            logger.debug("Dedup: skipping duplicate hall event %s", event_id)
            return

    channel_layer = get_channel_layer()
    try:
        async_to_sync(channel_layer.group_send)(
            hall_group_name(restaurant_id),
            {"type": "hall.event", "event": event},
        )
    except Exception:
        logger.exception("Failed to broadcast hall event for restaurant %s", restaurant_id)


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
            "event_id": _stable_event_id("HALL_TABLE_STATUS_CHANGED", table_id, current_status, session_id),
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
    layout_version_public_id: str,
    restaurant_public_id: str,
) -> None:
    _broadcast_hall_event(
        restaurant_id,
        {
            "event_name": "LAYOUT_PUBLISHED",
            "schema_version": "1",
            "event_id": _stable_event_id("LAYOUT_PUBLISHED", layout_version_id),
            "layout_version_public_id": layout_version_public_id,
            "restaurant_public_id": restaurant_public_id,
            "occurred_at": timezone.now().isoformat(),
        },
    )


def _send_to_staff_group(restaurant_id: int, event: dict[str, object]) -> None:
    channel_layer = get_channel_layer()
    try:
        async_to_sync(channel_layer.group_send)(
            staff_group_name(restaurant_id),
            {"type": "hall.event", "event": event},
        )
    except Exception:
        logger.exception(
            "Failed to broadcast event to staff group for restaurant %s",
            restaurant_id,
        )


def emit_hall_reservation_cancelled(
    restaurant_id: int,
    *,
    reservation_id: str,
    table_id: str,
    actor: User,
) -> None:
    event: dict[str, object] = {
        "event_name": "HALL_RESERVATION_CANCELLED",
        "schema_version": "1",
        "event_id": _stable_event_id("HALL_RESERVATION_CANCELLED", reservation_id, table_id),
        "reservation_id": reservation_id,
        "table_id": table_id,
        "actor_id": actor.pk,
        "actor_role": actor.role,
        "occurred_at": timezone.now().isoformat(),
    }
    _broadcast_hall_event(restaurant_id, event)
    _send_to_staff_group(restaurant_id, event)


def emit_hall_new_reservation(
    restaurant_id: int,
    *,
    reservation_id: str,
    table_id: str,
    start_at: str,
    end_at: str,
    actor: User,
) -> None:
    event: dict[str, object] = {
        "event_name": "HALL_NEW_RESERVATION",
        "schema_version": "1",
        "event_id": _stable_event_id("HALL_NEW_RESERVATION", reservation_id, table_id),
        "reservation_id": reservation_id,
        "table_id": table_id,
        "start_at": start_at,
        "end_at": end_at,
        "actor_id": actor.pk,
        "actor_role": actor.role,
        "occurred_at": timezone.now().isoformat(),
    }
    _broadcast_hall_event(restaurant_id, event)
    _send_to_staff_group(restaurant_id, event)


def emit_hall_preorder_status_changed(
    restaurant_id: int,
    *,
    reservation_id: str,
    status: str,
) -> None:
    """Tell the guest's booking list that their pre-order moved on.

    Carries the booking's public id and one of paid/cooking/ready — the same
    thing the reservation payload already exposes to whoever can read it, and
    nothing about the food or the money.
    """
    event: dict[str, object] = {
        "event_name": "HALL_PREORDER_STATUS_CHANGED",
        "schema_version": "1",
        "event_id": _stable_event_id("HALL_PREORDER_STATUS_CHANGED", reservation_id, status),
        "reservation_id": reservation_id,
        "status": status,
        "occurred_at": timezone.now().isoformat(),
    }
    _broadcast_hall_event(restaurant_id, event)
    _send_to_staff_group(restaurant_id, event)


def emit_preorder_status_for_reservation(restaurant_id: int, reservation: Reservation | None) -> None:
    """Resolve the booking's current pre-order state and push it, if it has one."""
    if reservation is None:
        return

    # Imported here, not at module scope: apps.reservations already imports
    # apps.orders, which imports this module.
    from apps.reservations.selectors import preorder_status_for_reservation

    status = preorder_status_for_reservation(reservation.pk)
    if status is None:
        return
    emit_hall_preorder_status_changed(
        restaurant_id,
        reservation_id=str(reservation.public_id),
        status=status,
    )


def emit_hall_zone_created(
    restaurant_id: int,
    *,
    zone_public_id: str,
    zone_name: str,
) -> None:
    _broadcast_hall_event(
        restaurant_id,
        {
            "event_name": "ZONE_CREATED",
            "schema_version": "1",
            "event_id": _stable_event_id("ZONE_CREATED", zone_public_id),
            "zone_public_id": zone_public_id,
            "zone_name": zone_name,
            "occurred_at": timezone.now().isoformat(),
        },
    )


def emit_hall_zone_updated(
    restaurant_id: int,
    *,
    zone_public_id: str,
    zone_name: str,
    zone_updated_at: str,
) -> None:
    # ``zone_updated_at`` (the zone's auto_now timestamp) is part of the event_id so each distinct
    # save produces a distinct id. Without it, every update to the same zone collides on the dedup
    # key and repeated renames within the dedup TTL would be silently dropped. Re-sends of the same
    # save still dedup, which is the intended idempotency.
    _broadcast_hall_event(
        restaurant_id,
        {
            "event_name": "ZONE_UPDATED",
            "schema_version": "1",
            "event_id": _stable_event_id("ZONE_UPDATED", zone_public_id, zone_updated_at),
            "zone_public_id": zone_public_id,
            "zone_name": zone_name,
            "occurred_at": timezone.now().isoformat(),
        },
    )


def emit_hall_reservations_updated(
    restaurant_id: int,
    *,
    table_ids: list[str],
) -> None:
    event: dict[str, object] = {
        "event_name": "HALL_RESERVATIONS_UPDATED",
        "schema_version": "1",
        "table_ids": table_ids,
        "occurred_at": timezone.now().isoformat(),
    }
    _broadcast_hall_event(restaurant_id, event)
    _send_to_staff_group(restaurant_id, event)


def emit_hall_zone_deleted(
    restaurant_id: int,
    *,
    zone_public_id: str,
) -> None:
    _broadcast_hall_event(
        restaurant_id,
        {
            "event_name": "ZONE_DELETED",
            "schema_version": "1",
            "event_id": _stable_event_id("ZONE_DELETED", zone_public_id),
            "zone_public_id": zone_public_id,
            "occurred_at": timezone.now().isoformat(),
        },
    )


def emit_hall_session_auto_extended(
    restaurant_id: int,
    *,
    table_id: str,
    ends_at: str,
    clamped_by: str,
) -> None:
    event: dict[str, object] = {
        "event_name": "HALL_SESSION_AUTO_EXTENDED",
        "schema_version": "1",
        "table_id": table_id,
        "ends_at": ends_at,
        "clamped_by": clamped_by,
        "occurred_at": timezone.now().isoformat(),
    }
    _broadcast_hall_event(restaurant_id, event)
    _send_to_staff_group(restaurant_id, event)
