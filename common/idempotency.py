from __future__ import annotations

import json
import uuid
from typing import Any

from django.core.cache import cache
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

IDEMPOTENCY_TIMEOUT: int = 60 * 60 * 24  # 24 hours


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
                {"idempotency_key": "Invalid Idempotency-Key format. Must be a valid UUIDv4."}
            ) from None
        return str(val)

    def get_cached_response(self, key: str) -> Response | None:
        cached = cache.get(f"idempotency:{key}")
        if cached is None:
            return None
        data: dict[str, Any] = json.loads(cached)
        return Response(data=data, status=data.get("_status", 201))

    def cache_response(self, key: str, response: Response) -> None:
        raw = response.data if response.data is not None else {}
        body: dict[str, Any] = {**raw, "_status": response.status_code}
        cache.set(f"idempotency:{key}", json.dumps(body), IDEMPOTENCY_TIMEOUT)
