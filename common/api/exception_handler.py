from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from common.exceptions import DomainError


def custom_exception_handler(
    exc: Exception, context: dict[str, Any]
) -> Response | None:
    if isinstance(exc, DomainError):
        return Response(
            {"detail": exc.default_detail, "code": exc.default_code},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return exception_handler(exc, context)
