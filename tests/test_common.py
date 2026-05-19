from rest_framework import status

from common.exceptions import DomainError, ReservationConflictError, error_payload


class TestDomainError:
    def test_default_values(self) -> None:
        exc = DomainError()
        assert exc.status_code == status.HTTP_400_BAD_REQUEST
        assert exc.default_code == "domain_error"

    def test_custom_detail(self) -> None:
        exc = DomainError(detail="Custom error")
        assert exc.detail == "Custom error"


class TestReservationConflictError:
    def test_status_code(self) -> None:
        exc = ReservationConflictError()
        assert exc.status_code == status.HTTP_409_CONFLICT

    def test_default_code(self) -> None:
        exc = ReservationConflictError()
        assert exc.default_code == "reservation_conflict"

    def test_custom_detail(self) -> None:
        exc = ReservationConflictError(detail="Table already booked")
        assert exc.detail == "Table already booked"


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
