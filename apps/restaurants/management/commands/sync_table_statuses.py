from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import Table, TableStatus


class Command(BaseCommand):
    help = (
        "Sync table statuses based on current reservations. "
        "Tables with a currently active reservation (start_at <= now < end_at) "
        "are set to RESERVED. Tables whose reservation window has passed are "
        "reverted to FREE. OCCUPIED tables (walk-in/seated guests) are not touched."
    )

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

        reserved = Table.objects.filter(
            id__in=tables_with_active_res,
            status__in=[TableStatus.FREE, TableStatus.RESERVED],
        ).update(status=TableStatus.RESERVED)

        freed = (
            Table.objects.filter(
                status=TableStatus.RESERVED,
            )
            .exclude(
                id__in=tables_with_active_res,
            )
            .update(status=TableStatus.FREE)
        )

        self.stdout.write(self.style.SUCCESS(f"Done. {reserved} marked as reserved, {freed} freed."))
