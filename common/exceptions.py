from http import HTTPStatus


class DomainError(Exception):
    default_detail = "A domain error occurred."
    default_code = "domain_error"
    default_status_code = HTTPStatus.BAD_REQUEST


class ReservationConflictError(DomainError):
    default_detail = "Reservation conflicts with an existing booking."
    default_code = "reservation_conflict"
    default_status_code = HTTPStatus.CONFLICT
