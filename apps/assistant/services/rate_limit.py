from __future__ import annotations

import logging
from datetime import datetime

from django.core.cache import cache
from django.utils import timezone

from common.exceptions import DomainError

logger = logging.getLogger(__name__)


class RateLimitExceededError(DomainError):
    default_detail = "You have reached the assistant message limit. Please try again later."
    default_code = "rate_limit"
    default_status_code = 429

    def __init__(self, *args: object, retry_after: int | None = None) -> None:
        super().__init__(*args)
        self.retry_after = retry_after


def _hour_bucket(now: datetime) -> str:
    return now.strftime("%Y%m%d%H")


def _day_bucket(now: datetime) -> str:
    return now.strftime("%Y%m%d")


def _increment(key: str, ttl: int) -> int:
    added = cache.add(key, 1, ttl)
    if added:
        return 1
    try:
        return int(cache.incr(key))
    except ValueError:
        return 1


def _under_cap(key: str, ttl: int, cap: int, now: datetime) -> bool:
    value = cache.get(key)
    if value is None:
        cache.set(key, 0, ttl)
        return True
    return int(value) < cap


def check_rate_limit(identity_key: str, restaurant_id: int, *, now: datetime | None = None) -> None:
    """Enforce hourly/daily caps keyed on the guest's authenticated identity.

    Runs before any model inference (FR-023): a hit raises ``RateLimitExceededError``
    carrying a ``retry_after`` hint, and no message is persisted or queued.
    """
    from django.conf import settings

    hourly_cap = int(getattr(settings, "ASSISTANT_HOURLY_CAP", 20))
    daily_cap = int(getattr(settings, "ASSISTANT_DAILY_CAP", 100))

    current = now or timezone.now()
    hour_key = f"assistant:cap:{restaurant_id}:{identity_key}:hour:{_hour_bucket(current)}"
    day_key = f"assistant:cap:{restaurant_id}:{identity_key}:day:{_day_bucket(current)}"

    # Fail-open on counter errors: a monitoring hiccup must not block a guest.
    try:
        if not _under_cap(hour_key, 60 * 60, hourly_cap, current):
            raise RateLimitExceededError(retry_after=3600)
        if not _under_cap(day_key, 86400, daily_cap, current):
            raise RateLimitExceededError(retry_after=3600)
        _increment(hour_key, 60 * 60)
        _increment(day_key, 86400)
    except RateLimitExceededError:
        raise
    except Exception:
        logger.exception("Assistant rate-limit check failed; allowing request.")


__all__ = ["RateLimitExceededError", "check_rate_limit"]
