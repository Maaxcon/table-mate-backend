from typing import Any

from rest_framework.response import Response
from rest_framework.views import exception_handler

from common.api.exceptions import DomainAPIException, error_payload
from common.exceptions import DomainError


def custom_api_exception_handler(
    exc: Exception, context: dict[str, Any]
) -> Response | None:
    if isinstance(exc, DomainError):
        exc = DomainAPIException(exc)

    response = exception_handler(exc, context)

    if response is not None:
        response.data = error_payload(
            detail=response.data.get("detail", str(exc)),
            code=getattr(exc, "get_codes", lambda: "invalid")(),
            status_code=response.status_code,
        )

    return response
