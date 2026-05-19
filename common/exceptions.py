from typing import Any

from rest_framework import status
from rest_framework.exceptions import APIException


class DomainError(APIException):
    status_code: int = status.HTTP_400_BAD_REQUEST
    default_detail = "A domain error occurred."
    default_code = "domain_error"


class ReservationConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Reservation conflicts with an existing booking."
    default_code = "reservation_conflict"


def error_payload(
    detail: str, code: str, status_code: int | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"detail": detail, "code": code}
    if status_code is not None:
        payload["status"] = status_code
    return payload
