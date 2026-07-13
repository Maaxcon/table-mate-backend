"""Order/cart services, split by concern.

Public callers import from ``apps.orders.services`` as before; this package
re-exports the API so the split into cart/sessions/walk_in is internal only.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any, cast

from .cart import (
    add_item_to_cart,
    create_order_with_items,
    emit_hall_table_status_changed,
    get_bill_order_items,
    open_session,
    pay_order_items,
    remove_item_from_cart,
    update_cart_item_quantity,
    update_session_status,
    void_order_item,
)
from .walk_in import create_walk_in_reservation

if TYPE_CHECKING:
    from apps.authentication.models import User
    from apps.orders.models import CartSession, Session
    from apps.reservations.models import Reservation
    from apps.restaurants.models import Table


def _sessions_module() -> Any:
    return import_module(".sessions", __name__)


def create_cart_session(*, restaurant_id: int, reservation_id: str, user: User) -> CartSession:
    return cast(
        CartSession,
        _sessions_module().create_cart_session(
            restaurant_id=restaurant_id,
            reservation_id=reservation_id,
            user=user,
        ),
    )


def ensure_active_cart_for_table(*, table: Table, user: User | None = None) -> CartSession:
    return cast(CartSession, _sessions_module().ensure_active_cart_for_table(table=table, user=user))


def close_stale_cart_sessions(*, restaurant_id: int | None = None, batch_size: int = 500) -> int:
    return cast(
        int,
        _sessions_module().close_stale_cart_sessions(restaurant_id=restaurant_id, batch_size=batch_size),
    )


def auto_extend_session(session: Session) -> dict[str, object]:
    return cast(dict[str, object], _sessions_module().auto_extend_session(session))


def auto_extend_all_sessions(restaurant_id: int | None = None) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], _sessions_module().auto_extend_all_sessions(restaurant_id))


def close_overdue_visit_sessions(*, batch_size: int = 200) -> int:
    return cast(int, _sessions_module().close_overdue_visit_sessions(batch_size=batch_size))


__all__ = [
    "add_item_to_cart",
    "create_order_with_items",
    "create_walk_in_reservation",
    "emit_hall_table_status_changed",
    "get_bill_order_items",
    "open_session",
    "pay_order_items",
    "remove_item_from_cart",
    "update_cart_item_quantity",
    "update_session_status",
    "void_order_item",
    "auto_extend_all_sessions",
    "auto_extend_session",
    "close_overdue_visit_sessions",
    "close_stale_cart_sessions",
    "create_cart_session",
    "ensure_active_cart_for_table",
]
