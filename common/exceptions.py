class DomainError(Exception):
    default_detail = "A domain error occurred."
    default_code = "domain_error"


class ReservationConflictError(DomainError):
    default_detail = "Reservation conflicts with an existing booking."
    default_code = "reservation_conflict"
