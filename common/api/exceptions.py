from typing import Any

from rest_framework import status
from rest_framework.exceptions import APIException

from common.exceptions import DomainError


class DomainAPIException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, exc: DomainError) -> None:
        super().__init__(detail=exc.default_detail, code=exc.default_code)


def error_payload(
    detail: str, code: str, status_code: int | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"detail": detail, "code": code}
    if status_code is not None:
        payload["status"] = status_code
    return payload
