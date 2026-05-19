from rest_framework import status
from rest_framework.exceptions import APIException

from common.exceptions import DomainError


class DomainAPIException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, exc: DomainError) -> None:
        super().__init__(detail=exc.default_detail, code=exc.default_code)
