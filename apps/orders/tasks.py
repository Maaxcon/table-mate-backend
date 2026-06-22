from celery import shared_task

from .services import close_stale_cart_sessions


@shared_task(name="orders.close_stale_carts")  # type: ignore[untyped-decorator]  # celery ships no type stubs
def close_stale_carts() -> int:
    """Periodic cleanup: close carts whose visit has ended. Scheduled via beat."""
    return close_stale_cart_sessions()
