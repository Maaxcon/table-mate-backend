from http import HTTPStatus


class DomainError(Exception):
    default_detail = "A domain error occurred."
    default_code = "domain_error"
    default_status_code = HTTPStatus.BAD_REQUEST


class ReservationConflictError(DomainError):
    default_detail = "Reservation conflicts with an existing booking."
    default_code = "reservation_conflict"
    default_status_code = HTTPStatus.CONFLICT

    def __init__(self, *args: object, conflicting_reservation_id: str | None = None) -> None:
        super().__init__(*args)
        self.conflicting_reservation_id = conflicting_reservation_id


class ReservationCancelError(DomainError):
    default_detail = "Only pending or active reservations can be cancelled."
    default_code = "reservation_cannot_cancel"
    default_status_code = HTTPStatus.BAD_REQUEST


class TableOccupiedError(DomainError):
    default_detail = "Table already has an active session."
    default_code = "table_occupied"
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


class NoActiveReservationError(DomainError):
    default_detail = "Table has no active reservation."
    default_code = "NO_ACTIVE_RESERVATION"
    default_status_code = HTTPStatus.NOT_FOUND


class ReservationNotYetActiveError(DomainError):
    """The table has a pending booking that has not been activated yet.

    Distinct from NO_ACTIVE_RESERVATION so the guest can be told their booking
    exists and when it starts, instead of "no booking". Carries the start time.
    """

    default_detail = "This table's booking has not started yet."
    default_code = "RESERVATION_NOT_YET_ACTIVE"
    default_status_code = HTTPStatus.NOT_FOUND

    def __init__(self, *args: object, start_at: str | None = None) -> None:
        super().__init__(*args)
        self.start_at = start_at


class CartSessionClosedError(DomainError):
    default_detail = "Cart session is closed."
    default_code = "cart_session_closed"
    default_status_code = HTTPStatus.CONFLICT


class EmptyCartError(DomainError):
    default_detail = "Cart has no items to check out."
    default_code = "empty_cart"
    default_status_code = HTTPStatus.BAD_REQUEST


class CartChangedError(DomainError):
    default_detail = "Some items are no longer available and were removed from the cart."
    default_code = "CART_CHANGED"
    default_status_code = HTTPStatus.CONFLICT

    def __init__(self, *args: object, removed: list[dict[str, str]] | None = None) -> None:
        super().__init__(*args)
        self.removed = removed or []


class MenuItemUnavailableError(DomainError):
    default_detail = "Menu item is not available."
    default_code = "menu_item_unavailable"
    default_status_code = HTTPStatus.BAD_REQUEST


class RestaurantClosedError(DomainError):
    default_detail = "The restaurant is closed right now."
    default_code = "restaurant_closed"
    default_status_code = HTTPStatus.CONFLICT


class WaiterCallCooldownError(DomainError):
    default_detail = "The waiter was already called for this table recently."
    default_code = "waiter_call_cooldown"
    default_status_code = HTTPStatus.TOO_MANY_REQUESTS


class ShiftCopyConflictError(DomainError):
    default_detail = "Some shifts already exist on target dates."
    default_code = "shift_copy_conflict"
    default_status_code = HTTPStatus.CONFLICT

class WaiterCallCooldownError(DomainError):
    default_detail = "The waiter was already called for this table recently."
    default_code = "waiter_call_cooldown"
    default_status_code = HTTPStatus.TOO_MANY_REQUESTS
