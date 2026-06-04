from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import Table, TableStatus


class Command(BaseCommand):
    help = "Set table statuses based on seeded reservations for demo purposes."

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        now = timezone.now()

        tables_with_active_res = set(
            Reservation.objects.filter(
                start_at__lte=now,
                end_at__gt=now,
                status__in=[ReservationStatus.PENDING, ReservationStatus.ACTIVE],
            )
            .exclude(table__isnull=True)
            .values_list("table_id", flat=True)
        )

        updated_reserved = Table.objects.filter(
            id__in=tables_with_active_res,
        ).update(status=TableStatus.RESERVED)

        self.stdout.write(self.style.SUCCESS(f"Done. {updated_reserved} tables marked as reserved."))
