from __future__ import annotations

import json
import logging
from contextlib import AbstractContextManager, nullcontext
from typing import Any, cast

from django.conf import settings
from django.core.cache import cache
from django_redis import get_redis_connection

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = getattr(settings, "NOTIFICATION_HISTORY_LIMIT", 50)
_DEFAULT_TTL = getattr(settings, "NOTIFICATION_HISTORY_TTL_SECONDS", 60 * 60 * 6)
_LOCK_TIMEOUT = getattr(settings, "NOTIFICATION_HISTORY_LOCK_TIMEOUT_SECONDS", 5)
_LOCK_BLOCKING_TIMEOUT = getattr(settings, "NOTIFICATION_HISTORY_LOCK_BLOCKING_TIMEOUT_SECONDS", 2)
_MAX_FIELD_LENGTH = max(getattr(settings, "NOTIFICATION_HISTORY_MAX_FIELD_LENGTH", 512), 8)
_MAX_LIST_LENGTH = max(getattr(settings, "NOTIFICATION_HISTORY_MAX_LIST_LENGTH", 25), 1)
_MAX_NESTED_DEPTH = max(getattr(settings, "NOTIFICATION_HISTORY_MAX_NESTED_DEPTH", 6), 1)
_NULL_CONTEXT: AbstractContextManager[None] = nullcontext()


def _history_key(restaurant_id: int) -> str:
    return f"notifications:history:{restaurant_id}"


def _history_lock_key(restaurant_id: int) -> str:
    return f"notifications:history-lock:{restaurant_id}"


def _history_lock(restaurant_id: int) -> AbstractContextManager[None]:
    lock_factory = getattr(cache, "lock", None)
    if callable(lock_factory):
        try:
            lock = lock_factory(
                _history_lock_key(restaurant_id),
                timeout=_LOCK_TIMEOUT,
                blocking_timeout=_LOCK_BLOCKING_TIMEOUT,
            )
            return cast(AbstractContextManager[None], lock)
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed to create notification history lock for restaurant %s", restaurant_id)
    return _NULL_CONTEXT


def _truncate_string(value: str) -> str:
    if len(value) <= _MAX_FIELD_LENGTH:
        return value
    if _MAX_FIELD_LENGTH <= 3:
        return value[:_MAX_FIELD_LENGTH]
    return f"{value[: _MAX_FIELD_LENGTH - 3]}..."


def _sanitize_value(value: Any, *, depth: int = 0) -> Any:
    if isinstance(value, str):
        return _truncate_string(value)
    if isinstance(value, bytes):
        return _truncate_string(value.decode("utf-8", "replace"))
    if isinstance(value, (int, float, bool)) or value is None:
        return value

    if depth >= _MAX_NESTED_DEPTH:
        if isinstance(value, dict):
            return {}
        if isinstance(value, (list, tuple, set)):
            return []
        return _truncate_string(str(value)) if not isinstance(value, (int, float, bool)) else value

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_str = key if isinstance(key, str) else str(key)
            sanitized[_truncate_string(key_str)] = _sanitize_value(item, depth=depth + 1)
        return sanitized

    if isinstance(value, (list, tuple, set)):
        sanitized_list: list[Any] = []
        for item in list(value)[:_MAX_LIST_LENGTH]:
            sanitized_list.append(_sanitize_value(item, depth=depth + 1))
        return sanitized_list

    return _truncate_string(str(value))


def _sanitize_event(event: dict[str, Any]) -> dict[str, Any]:
    sanitized = _sanitize_value(event)
    if isinstance(sanitized, dict):
        return sanitized
    return {"type": "UNKNOWN", "data": sanitized}


def store_notification_event(restaurant_id: int, event: dict[str, Any]) -> None:
    """Persist the latest staff notification for a restaurant.

    Notifications are stored newest-first with a bounded history length. Payloads
    are sanitized/truncated to cap untrusted data volume before persistence.
    """

    sanitized_event = _sanitize_event(event)
    if _persist_history_via_redis(restaurant_id, sanitized_event):
        return

    _persist_history_via_cache(restaurant_id, sanitized_event)


def get_notification_history(restaurant_id: int, limit: int | None = None) -> list[dict[str, Any]]:
    """Return the stored notifications for a restaurant, oldest-first."""

    slice_limit = limit if isinstance(limit, int) and limit > 0 else _DEFAULT_LIMIT
    history = _load_history_via_redis(restaurant_id, slice_limit)
    if history is not None:
        return history

    return _load_history_via_cache(restaurant_id, slice_limit)


def _persist_history_via_redis(restaurant_id: int, event: dict[str, Any]) -> bool:
    try:
        conn = get_redis_connection("default")
    except Exception:
        return False

    serialized = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
    key = _history_key(restaurant_id)

    try:
        pipeline = conn.pipeline()
        pipeline.lpush(key, serialized)
        pipeline.ltrim(key, 0, _DEFAULT_LIMIT - 1)
        if _DEFAULT_TTL > 0:
            pipeline.expire(key, _DEFAULT_TTL)
        pipeline.execute()
        return True
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("Failed to persist notification history via Redis for restaurant %s", restaurant_id)
        return False


def _load_history_via_redis(restaurant_id: int, slice_limit: int) -> list[dict[str, Any]] | None:
    try:
        conn = get_redis_connection("default")
    except Exception:
        return None

    key = _history_key(restaurant_id)
    try:
        raw_events = conn.lrange(key, 0, max(slice_limit - 1, 0))
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("Failed to load notification history via Redis for restaurant %s", restaurant_id)
        return None

    if not raw_events:
        try:
            key_exists = bool(conn.exists(key))
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed to check Redis history key existence for restaurant %s", restaurant_id)
            return None

        if not key_exists:
            return None
        return []

    decoded: list[dict[str, Any]] = []
    for payload in reversed(raw_events):
        try:
            text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else str(payload)
            event = json.loads(text)
            if isinstance(event, dict):
                decoded.append(event)
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed to decode notification history payload for restaurant %s", restaurant_id)
    return decoded


def _persist_history_via_cache(restaurant_id: int, event: dict[str, Any]) -> None:
    key = _history_key(restaurant_id)

    def _persist() -> None:
        try:
            history = cache.get(key)
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed to load notification history for restaurant %s", restaurant_id)
            history = None

        if not isinstance(history, list):
            history = []

        history.insert(0, event)
        if len(history) > _DEFAULT_LIMIT:
            del history[_DEFAULT_LIMIT:]

        try:
            cache.set(key, history, timeout=_DEFAULT_TTL)
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed to persist notification history for restaurant %s", restaurant_id)

    lock_cm = _history_lock(restaurant_id)
    if lock_cm is _NULL_CONTEXT:
        _persist()
        return

    try:
        with lock_cm:
            _persist()
            return
    except Exception:  # pragma: no cover - defensive logging
        logger.exception(
            "Failed to lock notification history for restaurant %s; falling back to unlocked write",
            restaurant_id,
        )

    _persist()


def _load_history_via_cache(restaurant_id: int, slice_limit: int) -> list[dict[str, Any]]:
    key = _history_key(restaurant_id)
    try:
        history = cache.get(key)
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("Failed to load notification history for restaurant %s", restaurant_id)
        history = None

    if not isinstance(history, list) or not history:
        return []

    recent = history[:slice_limit]
    return list(reversed(recent))
