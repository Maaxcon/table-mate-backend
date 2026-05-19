from typing import Any
from unittest.mock import MagicMock, patch

from rest_framework import status
from rest_framework.response import Response

from common.api.exception_handler import custom_exception_handler
from common.api.exceptions import DomainAPIException, error_payload
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


class TestDomainAPIException:
    def test_status_code(self) -> None:
        exc = DomainAPIException(DomainError())
        assert exc.status_code == status.HTTP_400_BAD_REQUEST

    def test_detail_from_domain_error(self) -> None:
        exc = DomainAPIException(DomainError())
        assert exc.detail == "A domain error occurred."

    def test_detail_from_reservation_conflict(self) -> None:
        exc = DomainAPIException(ReservationConflictError())
        assert exc.detail == "Reservation conflicts with an existing booking."


class TestErrorPayload:
    def test_minimal(self) -> None:
        result = error_payload("something broke", "err_code")
        assert result == {"detail": "something broke", "code": "err_code"}

    def test_with_status(self) -> None:
        result = error_payload("not found", "not_found", status_code=404)
        assert result == {
            "detail": "not found",
            "code": "not_found",
            "status": 404,
        }


class TestCustomExceptionHandler:
    def test_injects_code_for_domain_error(self) -> None:
        context: dict[str, Any] = {
            "view": MagicMock(),
            "request": MagicMock(),
            "args": (),
            "kwargs": {},
        }
        exc = DomainError()

        with patch("common.api.exception_handler.exception_handler") as mock_handler:
            mock_handler.return_value = Response({"detail": "test"}, status=400)
            response = custom_exception_handler(exc, context)

        assert response is not None
        assert response.data["code"] == "domain_error"

    def test_does_not_modify_non_domain_error(self) -> None:
        context: dict[str, Any] = {
            "view": MagicMock(),
            "request": MagicMock(),
            "args": (),
            "kwargs": {},
        }
        exc = ValueError("test")

        with patch("common.api.exception_handler.exception_handler") as mock_handler:
            mock_handler.return_value = Response({"detail": "test"}, status=400)
            response = custom_exception_handler(exc, context)

        assert response is not None
        assert "code" not in response.data

    def test_returns_none_when_unhandled(self) -> None:
        context: dict[str, Any] = {
            "view": MagicMock(),
            "request": MagicMock(),
            "args": (),
            "kwargs": {},
        }
        exc = DomainError()

        with patch("common.api.exception_handler.exception_handler") as mock_handler:
            mock_handler.return_value = None
            response = custom_exception_handler(exc, context)

        assert response is None
