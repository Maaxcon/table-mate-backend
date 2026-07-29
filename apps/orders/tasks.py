from celery import shared_task

from .services import (
    auto_extend_all_sessions,
    close_overdue_visit_sessions,
    close_stale_cart_sessions,
    inject_scheduled_preorders,
)


@shared_task(name="orders.close_stale_carts")  # type: ignore[untyped-decorator]  # celery ships no type stubs
def close_stale_carts() -> int:
    """Periodic cleanup: close carts whose visit has ended. Scheduled via beat."""
    return close_stale_cart_sessions()


@shared_task(name="orders.auto_extend_sessions")  # type: ignore[untyped-decorator]
def auto_extend_sessions() -> list[dict[str, object]]:
    """Periodic auto-extend: extend open sessions nearing their end time."""
    return auto_extend_all_sessions()


@shared_task(name="orders.close_overdue_sessions")  # type: ignore[untyped-decorator]
def close_overdue_sessions() -> int:
    """Periodic cleanup: auto-close OPEN visits overdue past grace."""
    return close_overdue_visit_sessions()


@shared_task(name="orders.inject_scheduled_preorders")  # type: ignore[untyped-decorator]
def inject_scheduled_preorders_task() -> int:
    """Periodic: turn paid pre-orders into kitchen tickets near arrival."""
    return inject_scheduled_preorders()
