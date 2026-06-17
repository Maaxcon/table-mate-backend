from typing import Any

from django.core.management.base import BaseCommand

from apps.orders.models import VoidReason


class Command(BaseCommand):
    help = "Seed void reasons"

    def handle(self, *args: Any, **options: Any) -> None:
        reasons = [
            ("mispick", "Mispick"),
            ("guest_changed_mind", "Guest changed mind"),
            ("quality_issue", "Quality issue"),
            ("out_of_stock", "Out of stock"),
            ("preparation_error", "Preparation error"),
            ("duplicate_order", "Duplicate order"),
        ]

        created = 0
        for code, label in reasons:
            _, was_created = VoidReason.objects.get_or_create(code=code, defaults={"label": label})
            if was_created:
                created += 1

        self.stdout.write(self.style.SUCCESS(f"Done: {created} void reasons created"))
