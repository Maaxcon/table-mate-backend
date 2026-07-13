from __future__ import annotations

import copy
import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = getattr(settings, "NOTIFICATION_HISTORY_LIMIT", 50)
_DEFAULT_TTL = getattr(settings, "NOTIFICATION_HISTORY_TTL_SECONDS", 60 * 60 * 6)


def _history_key(restaurant_id: int) -> str:
    return f"notifications:history:{restaurant_id}"


def store_notification_event(restaurant_id: int, event: dict[str, Any]) -> None:
    """Persist the latest staff notification for a restaurant.

    Notifications are stored newest-first with a bounded history length. A copy of
    the event is persisted to avoid accidental mutation by callers.
    """

    key = _history_key(restaurant_id)
    try:
        history = cache.get(key)
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("Failed to load notification history for restaurant %s", restaurant_id)
        history = None

    if not isinstance(history, list):
        history = []

    history.insert(0, copy.deepcopy(event))
    if len(history) > _DEFAULT_LIMIT:
        del history[_DEFAULT_LIMIT:]

    try:
        cache.set(key, history, timeout=_DEFAULT_TTL)
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("Failed to persist notification history for restaurant %s", restaurant_id)


def get_notification_history(restaurant_id: int, limit: int | None = None) -> list[dict[str, Any]]:
    """Return the stored notifications for a restaurant, oldest-first."""

    key = _history_key(restaurant_id)
    try:
        history = cache.get(key)
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("Failed to load notification history for restaurant %s", restaurant_id)
        history = None

    if not isinstance(history, list) or not history:
        return []

    slice_limit = limit if isinstance(limit, int) and limit > 0 else _DEFAULT_LIMIT
    recent = history[:slice_limit]
    # Stored newest-first, so replay oldest-first.
    return list(reversed(recent))
