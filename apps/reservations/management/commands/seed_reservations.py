from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.authentication.models import RoleCode, User
from apps.orders.models import Session
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Restaurant, RestaurantSettings, Table


class Command(BaseCommand):
    help = "Seed reservation data for restaurants"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--restaurant-id",
            type=int,
            help="Restaurant ID to seed (seeds all if omitted)",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        restaurants = Restaurant.objects.all()
        if options["restaurant_id"]:
            restaurants = restaurants.filter(pk=options["restaurant_id"])
        if not restaurants.exists():
            self.stdout.write(self.style.WARNING("No restaurants found. Create one first."))
            return

        created_reservations = 0
        now = timezone.now()

        for restaurant in restaurants:
            self.stdout.write(f"Seeding reservations for restaurant: {restaurant.name}")

            # Index tables by public_number (e.g. "T1"). Table.Meta.ordering sorts
            # public_number lexicographically ("T1", "T10", "T2", ...), so positional
            # indexing does NOT match table numbers — always look tables up by number.
            tables_by_number = {
                t.public_number: t
                for t in Table.objects.filter(restaurant=restaurant, active=True)
            }
            if not tables_by_number:
                self.stdout.write(self.style.WARNING(f"No active tables for {restaurant.name}. Skipping."))
                continue

            # Delete all existing sessions and reservations for a clean seed
            Session.objects.filter(restaurant=restaurant).delete()
            Reservation.objects.filter(restaurant=restaurant).delete()

            reservations_config: list[dict[str, Any]] = [
                # ── Active reservations (ongoing now → sessions created → OCCUPIED) ──
                {
                    "table": "T1",
                    "customer_name": "Олександр Коваленко",
                    "guest_count": 2,
                    "start_at": now - timedelta(hours=1),
                    "end_at": now + timedelta(hours=2),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.ACTIVE,
                    "notes": "Алергія на горіхи",
                },
                {
                    "table": "T2",
                    "customer_name": "Марія Шевченко",
                    "guest_count": 4,
                    "start_at": now - timedelta(minutes=45),
                    "end_at": now + timedelta(hours=1, minutes=30),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.ACTIVE,
                    "notes": None,
                },
                {
                    "table": "T3",
                    "customer_name": "Дмитро Бондаренко",
                    "guest_count": 3,
                    "start_at": now - timedelta(minutes=90),
                    "end_at": now + timedelta(minutes=90),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.ACTIVE,
                    "notes": "Дитячий стільчик",
                },
                {
                    "table": "T5",
                    "customer_name": "Ірина Мельник",
                    "guest_count": 5,
                    "start_at": now - timedelta(minutes=30),
                    "end_at": now + timedelta(hours=3),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.ACTIVE,
                    "notes": None,
                },
                # ── Pending reservations (upcoming soon → no sessions → RESERVED) ──
                {
                    "table": "T8",
                    "customer_name": "Андрій Ткаченко",
                    "guest_count": 4,
                    "start_at": now + timedelta(minutes=8),
                    "end_at": now + timedelta(hours=2, minutes=30),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.PENDING,
                    "notes": "Потрібен високий стільчик",
                },
                {
                    "table": "T9",
                    "customer_name": "Олена Кравченко",
                    "guest_count": 3,
                    "start_at": now + timedelta(minutes=12),
                    "end_at": now + timedelta(hours=2),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.PENDING,
                    "notes": None,
                },
                # ── Pending reservation (within 15 min window → shows RESERVED) ──
                {
                    "table": "T10",
                    "customer_name": "Василь Лисенко",
                    "guest_count": 4,
                    "start_at": now + timedelta(minutes=5),
                    "end_at": now + timedelta(hours=2),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.PENDING,
                    "notes": None,
                },
                # ── Past reservations (now completed, no effect on floor plan) ──
                {
                    "table": "T4",
                    "customer_name": "Наталія Попова",
                    "guest_count": 6,
                    "start_at": now - timedelta(days=2),
                    "end_at": now - timedelta(days=2) + timedelta(hours=2),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.COMPLETED,
                    "notes": "День народження",
                },
                {
                    "table": "T7",
                    "customer_name": "Сергій Іваненко",
                    "guest_count": 8,
                    "start_at": now - timedelta(days=1),
                    "end_at": now - timedelta(days=1) + timedelta(hours=2),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.COMPLETED,
                    "notes": None,
                },
                # ── Cancelled reservation ──
                {
                    "table": "T6",
                    "customer_name": "Тетяна Савченко",
                    "guest_count": 4,
                    "start_at": now + timedelta(days=3),
                    "end_at": now + timedelta(days=3, hours=2),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.CANCELLED,
                    "notes": "Захворіли",
                },
            ]

            for data in reservations_config:
                table = tables_by_number.get(data["table"])
                if table is None:
                    # This restaurant's layout doesn't include the table — skip
                    # rather than wrapping onto an unrelated one.
                    continue

                reservation, was_created = Reservation.objects.get_or_create(
                    restaurant=restaurant,
                    table=table,
                    start_at=data["start_at"],
                    defaults={
                        "customer_name": data["customer_name"],
                        "guest_count": data["guest_count"],
                        "end_at": data["end_at"],
                        "status": data["status"],
                        "notes": data["notes"],
                    },
                )
                if was_created:
                    created_reservations += 1

                # Create Session for ACTIVE reservations (required for is_occupied)
                if data["status"] == ReservationStatus.ACTIVE:
                    session_exists = Session.objects.filter(reservation=reservation).exists()
                    if not session_exists:
                        staff_user = User.objects.filter(
                            restaurant=restaurant,
                            role__in=[RoleCode.WAITER, RoleCode.ADMIN],
                        ).first()
                        currency = "EUR"
                        try:
                            currency = restaurant.settings.currency
                        except RestaurantSettings.DoesNotExist:
                            pass
                        Session.objects.create(
                            restaurant=restaurant,
                            table=table,
                            reservation=reservation,
                            opened_by=staff_user,
                            guest_count=reservation.guest_count,
                            currency=currency,
                            opened_at=reservation.start_at,
                        )

        self.stdout.write(self.style.SUCCESS(f"Done: {created_reservations} reservations created"))
