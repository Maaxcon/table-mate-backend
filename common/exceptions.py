from http import HTTPStatus


class DomainError(Exception):
    default_detail = "A domain error occurred."
    default_code = "domain_error"
    default_status_code = HTTPStatus.BAD_REQUEST


class ReservationConflictError(DomainError):
    default_detail = "Reservation conflicts with an existing booking."
    default_code = "reservation_conflict"
    default_status_code = HTTPStatus.CONFLICT


class CartSessionNotFoundError(DomainError):
    default_detail = "Cart session not found."
    default_code = "cart_session_not_found"
    default_status_code = HTTPStatus.NOT_FOUND


class CartItemNotFoundError(DomainError):
    default_detail = "Cart item not found."
    default_code = "cart_item_not_found"
    default_status_code = HTTPStatus.NOT_FOUND


class MenuItemNotFoundError(DomainError):
    default_detail = "Menu item not found."
    default_code = "menu_item_not_found"
    default_status_code = HTTPStatus.NOT_FOUND


class ReservationNotFoundError(DomainError):
    default_detail = "Reservation not found."
    default_code = "reservation_not_found"
    default_status_code = HTTPStatus.NOT_FOUND
