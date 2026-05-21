from typing import Any
from unittest.mock import MagicMock, patch

from rest_framework import status
from rest_framework.response import Response

from common.api.exception_handler import custom_exception_handler
from common.exceptions import DomainError, ReservationConflictError


class TestDomainError:
    def test_default_detail(self) -> None:
        assert DomainError().default_detail == "A domain error occurred."

    def test_default_code(self) -> None:
        assert DomainError().default_code == "domain_error"

    def test_is_exception_subclass(self) -> None:
        assert isinstance(DomainError(), Exception)


class TestReservationConflictError:
    def test_default_detail(self) -> None:
        assert (
            ReservationConflictError().default_detail
            == "Reservation conflicts with an existing booking."
        )

    def test_default_code(self) -> None:
        assert ReservationConflictError().default_code == "reservation_conflict"

    def test_is_domain_error_subclass(self) -> None:
        assert isinstance(ReservationConflictError(), DomainError)


class TestCustomExceptionHandler:
    def test_returns_response_for_domain_error(self) -> None:
        context: dict[str, Any] = {
            "view": MagicMock(),
            "request": MagicMock(),
            "args": (),
            "kwargs": {},
        }
        response = custom_exception_handler(DomainError(), context)

        assert response is not None
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data == {
            "detail": "A domain error occurred.",
            "code": "domain_error",
        }

    def test_returns_response_for_reservation_conflict(self) -> None:
        context: dict[str, Any] = {
            "view": MagicMock(),
            "request": MagicMock(),
            "args": (),
            "kwargs": {},
        }
        response = custom_exception_handler(ReservationConflictError(), context)

        assert response is not None
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data == {
            "detail": "Reservation conflicts with an existing booking.",
            "code": "reservation_conflict",
        }

    def test_delegates_non_domain_error(self) -> None:
        context: dict[str, Any] = {
            "view": MagicMock(),
            "request": MagicMock(),
            "args": (),
            "kwargs": {},
        }

        with patch("common.api.exception_handler.exception_handler") as mock_handler:
            mock_handler.return_value = Response({"detail": "test"}, status=400)
            response = custom_exception_handler(ValueError("test"), context)

        assert response is not None
        assert response.data == {"detail": "test"}

    def test_returns_none_for_unhandled_non_domain_error(self) -> None:
        context: dict[str, Any] = {
            "view": MagicMock(),
            "request": MagicMock(),
            "args": (),
            "kwargs": {},
        }

        with patch("common.api.exception_handler.exception_handler") as mock_handler:
            mock_handler.return_value = None
            response = custom_exception_handler(ValueError("test"), context)

        assert response is None
