from django.http import HttpRequest
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from common.api.exception_handler import custom_exception_handler
from common.exceptions import DomainError, ReservationConflictError


class _DomainErrorView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request: Request) -> Response:
        raise DomainError()


class _ReservationConflictView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request: Request) -> Response:
        raise ReservationConflictError()


class _PermissionDeniedView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request: Request) -> Response:
        raise PermissionDenied("not allowed")


class TestExceptionHandlerEndToEnd:
    def test_domain_error_returns_400(self) -> None:
        view = _DomainErrorView.as_view()
        request = APIRequestFactory().get("/")
        response = view(request)
        assert response.status_code == 400
        assert response.data == {
            "detail": "A domain error occurred.",
            "code": "domain_error",
        }

    def test_reservation_conflict_returns_409(self) -> None:
        view = _ReservationConflictView.as_view()
        request = APIRequestFactory().get("/")
        response = view(request)
        assert response.status_code == 409
        assert response.data == {
            "detail": "Reservation conflicts with an existing booking.",
            "code": "reservation_conflict",
        }

    def test_non_domain_error_delegates(self) -> None:
        view = _PermissionDeniedView.as_view()
        request = APIRequestFactory().get("/")
        response = view(request)
        assert response.status_code == 403
        assert response.data == {"detail": "not allowed"}

    def test_handler_returns_none_for_unhandled_non_drf_error(self) -> None:
        context: dict[str, object] = {"view": None, "args": (), "kwargs": {}, "request": HttpRequest()}
        result = custom_exception_handler(ValueError("oops"), context)
        assert result is None
