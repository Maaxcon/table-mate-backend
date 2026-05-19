from typing import Any

from rest_framework.response import Response
from rest_framework.views import exception_handler

from common.exceptions import DomainError


def custom_exception_handler(
    exc: Exception, context: dict[str, Any]
) -> Response | None:
    response = exception_handler(exc, context)
    if response is not None and isinstance(exc, DomainError):
        response.data["code"] = exc.default_code
    return response
