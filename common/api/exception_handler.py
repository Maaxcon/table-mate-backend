from typing import Any

from django.db import IntegrityError
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import exception_handler

from common.exceptions import DomainError

_PERMISSION_DENIED_CODE = "permission_denied"


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, DomainError):
        data: dict[str, Any] = {
            "detail": str(exc) or exc.default_detail,
            "code": exc.default_code,
        }
        conflicting_id = getattr(exc, "conflicting_reservation_id", None)
        if conflicting_id is not None:
            data["conflicting_reservation_id"] = str(conflicting_id)
        return Response(data, status=exc.default_status_code)
    if isinstance(exc, PermissionDenied):
        return Response(
            {"detail": exc.detail, "code": _PERMISSION_DENIED_CODE},
            status=exc.status_code,
        )
    if isinstance(exc, IntegrityError):
        return Response(
            {"detail": "The request conflicts with existing data.", "code": "integrity_error"},
            status=409,
        )
    return exception_handler(exc, context)
