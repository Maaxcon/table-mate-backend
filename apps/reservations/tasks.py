from celery import shared_task

from .services import expire_noshow_reservations


@shared_task(name="reservations.expire_noshow_reservations")  # type: ignore[untyped-decorator]
def expire_noshow_reservations_task() -> int:
    """Periodic cleanup: auto-cancel PENDING reservations overdue past grace."""
    return expire_noshow_reservations()
