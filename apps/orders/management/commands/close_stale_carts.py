from typing import Any

from django.core.management.base import BaseCommand

from apps.orders.services import close_stale_cart_sessions


class Command(BaseCommand):
    help = "Close active cart sessions whose reservation is completed, cancelled, or past its end time."

    def handle(self, *args: Any, **options: Any) -> None:
        closed = close_stale_cart_sessions()
        self.stdout.write(f"Closed {closed} stale cart session(s).")
