from typing import Any

from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import exception_handler

from common.exceptions import DomainError

_PERMISSION_DENIED_CODE = "permission_denied"


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, DomainError):
        return Response(
            {"detail": exc.default_detail, "code": exc.default_code},
            status=exc.default_status_code,
        )
    if isinstance(exc, PermissionDenied):
        return Response(
            {"detail": exc.detail, "code": _PERMISSION_DENIED_CODE},
            status=exc.status_code,
        )
    return exception_handler(exc, context)
