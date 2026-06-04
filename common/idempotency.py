from __future__ import annotations

import json
import uuid
from typing import Any

from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

IDEMPOTENCY_TIMEOUT: int = 60 * 60 * 24  # 24 hours
IDEMPOTENCY_PROCESSING_TIMEOUT: int = 60 * 10  # 10 minutes
_PROCESSING_MARKER = "::processing"


def _idempotency_cache_key(key: str, request: Request) -> str:
    user = request.user
    uid = str(getattr(user, "pk", "anon"))
    return f"idempotency:{uid}:{key}"


class IdempotencyKeyMixin:
    idempotency_header: str = "HTTP_IDEMPOTENCY_KEY"

    def validate_idempotency_key(self, request: Request) -> str | None:
        raw = request.META.get(self.idempotency_header, "")
        if not raw:
            return None
        try:
            val = uuid.UUID(raw)
        except (ValueError, AttributeError):
            raise ValidationError(
                {"idempotency_key": "Invalid Idempotency-Key format. Must be a valid UUID."}
            ) from None
        return str(val)

    def get_cached_response(self, key: str, request: Request) -> Response | None:
        """
        Return the cached response for an idempotency key, if one exists.

        The cached response is returned regardless of whether the current
        request body matches the original — the idempotency guarantee only
        covers at-most-once execution for any caller-provided key.  Callers
        that need request-body validation on cache hit (i.e. to reject a
        reused key with a different payload) should hash the request body
        alongside the response during cache_response and compare here.
        """
        cache_key = _idempotency_cache_key(key, request)
        cached = cache.get(cache_key)
        if cached is None:
            return None
        data: dict[str, Any] = json.loads(cached)
        status_code = data.pop("_status", 201)
        return Response(data=data, status=status_code)

    def reserve_key(self, key: str, request: Request) -> bool:
        cache_key = _idempotency_cache_key(key, request)
        return cache.add(cache_key, _PROCESSING_MARKER, IDEMPOTENCY_PROCESSING_TIMEOUT)

    def release_key(self, key: str, request: Request) -> None:
        cache_key = _idempotency_cache_key(key, request)
        cache.delete(cache_key)

    def cache_response(self, key: str, response: Response, request: Request) -> None:
        cache_key = _idempotency_cache_key(key, request)
        raw = response.data if response.data is not None else {}
        body: dict[str, Any] = {**raw, "_status": response.status_code}
        cache.set(cache_key, DjangoJSONEncoder().encode(body), IDEMPOTENCY_TIMEOUT)
