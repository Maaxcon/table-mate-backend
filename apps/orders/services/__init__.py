"""Order/cart services, split by concern.

Public callers import from ``apps.orders.services`` as before; this package
re-exports the API so the split into cart/sessions/walk_in is internal only.
"""

from importlib import import_module

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

_SESSION_EXPORTS = {
    "auto_extend_all_sessions",
    "auto_extend_session",
    "close_overdue_visit_sessions",
    "close_stale_cart_sessions",
    "create_cart_session",
    "ensure_active_cart_for_table",
}


def __getattr__(name: str) -> object:
    if name in _SESSION_EXPORTS:
        module = import_module(".sessions", __name__)
        return getattr(module, name)
    # Backwards compat for any caller still importing these directly
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
