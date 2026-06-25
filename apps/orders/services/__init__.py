"""Order/cart services, split by concern.

Public callers import from ``apps.orders.services`` as before; this package
re-exports the API so the split into cart/sessions/walk_in is internal only.
"""

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
from .sessions import (
    close_stale_cart_sessions,
    create_cart_session,
    ensure_active_cart_for_table,
)
from .walk_in import create_walk_in_reservation


def __getattr__(name: str) -> object:
    # Backwards compat for any caller still importing these directly
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "add_item_to_cart",
    "close_stale_cart_sessions",
    "create_cart_session",
    "create_order_with_items",
    "create_walk_in_reservation",
    "emit_hall_table_status_changed",
    "ensure_active_cart_for_table",
    "get_bill_order_items",
    "open_session",
    "pay_order_items",
    "remove_item_from_cart",
    "update_cart_item_quantity",
    "update_session_status",
    "void_order_item",
]
