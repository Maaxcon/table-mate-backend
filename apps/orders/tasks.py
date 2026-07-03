from celery import shared_task

from .services import auto_extend_all_sessions, close_stale_cart_sessions


@shared_task(name="orders.close_stale_carts")  # type: ignore[untyped-decorator]  # celery ships no type stubs
def close_stale_carts() -> int:
    """Periodic cleanup: close carts whose visit has ended. Scheduled via beat."""
    return close_stale_cart_sessions()


@shared_task(name="orders.auto_extend_sessions")  # type: ignore[untyped-decorator]
def auto_extend_sessions() -> list[dict[str, object]]:
    """Periodic auto-extend: extend open sessions nearing their end time."""
    return auto_extend_all_sessions()
