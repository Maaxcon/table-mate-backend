from collections import defaultdict
from datetime import timedelta
from itertools import count
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.authentication.models import RoleCode, User
from apps.orders.models import Session
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Restaurant, RestaurantSettings, Table


_RESERVATIONS: dict[str, list[dict[str, Any]]] = {
    "UniTable": [
        # ── Active reservations (ongoing now → sessions created → OCCUPIED) ──
        {
            "table": "kathe",
            "customer_name": "Дмитро Бондаренко",
            "guest_count": 1,
            "start_at": None,  # filled in handle()
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.ACTIVE,
            "notes": None,
        },
        {
            "table": "marie",
            "customer_name": "Олександр Коваленко",
            "guest_count": 1,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.ACTIVE,
            "notes": "Алергія на горіхи",
        },
        {
            "table": "T1.5",
            "customer_name": "Марія Шевченко",
            "guest_count": 3,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.ACTIVE,
            "notes": None,
        },
        {
            "table": "переговорка",
            "customer_name": "Ірина Мельник",
            "guest_count": 5,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.ACTIVE,
            "notes": "Потрібен проектор",
        },
        {
            "table": "T5",
            "customer_name": "Андрій Ткаченко",
            "guest_count": 6,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.ACTIVE,
            "notes": None,
        },
        {
            "table": "T8",
            "customer_name": "Олег Козак",
            "guest_count": 4,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.ACTIVE,
            "notes": "На терасі",
        },
        # ── Pending reservations (upcoming soon → no sessions → RESERVED) ──
        {
            "table": "T3",
            "customer_name": "Олена Кравченко",
            "guest_count": 4,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.PENDING,
            "notes": None,
        },
        {
            "table": "T4",
            "customer_name": "Василь Лисенко",
            "guest_count": 6,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.PENDING,
            "notes": "День народження",
        },
        {
            "table": "T6.5",
            "customer_name": "Тетяна Савченко",
            "guest_count": 4,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.PENDING,
            "notes": None,
        },
        {
            "table": "mini",
            "customer_name": "Катерина Левченко",
            "guest_count": 2,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.PENDING,
            "notes": None,
        },
        {
            "table": "T7",
            "customer_name": "Віталій Шевчук",
            "guest_count": 4,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.PENDING,
            "notes": "Вечірка",
        },
        # ── Past reservations (now completed, no effect on floor plan) ──
        {
            "table": "T1",
            "customer_name": "Наталія Попова",
            "guest_count": 3,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.COMPLETED,
            "notes": "Річниця",
        },
        {
            "table": "T6",
            "customer_name": "Сергій Іваненко",
            "guest_count": 4,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.COMPLETED,
            "notes": None,
        },
        # ── Cancelled reservation ──
        {
            "table": "T2",
            "customer_name": "Юрій Ковальчук",
            "guest_count": 4,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.CANCELLED,
            "notes": "Скасував бронювання",
        },
    ],
    "Table Mate Terrace": [
        # ── Active reservations ──
        {
            "table": "T1",
            "customer_name": "Олександр Коваленко",
            "guest_count": 2,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.ACTIVE,
            "notes": "Алергія на горіхи",
        },
        {
            "table": "T2",
            "customer_name": "Марія Шевченко",
            "guest_count": 4,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.ACTIVE,
            "notes": None,
        },
        {
            "table": "T3",
            "customer_name": "Дмитро Бондаренко",
            "guest_count": 3,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.ACTIVE,
            "notes": "Дитячий стільчик",
        },
        {
            "table": "T5",
            "customer_name": "Ірина Мельник",
            "guest_count": 5,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.ACTIVE,
            "notes": None,
        },
        # ── Pending reservations ──
        {
            "table": "T4",
            "customer_name": "Андрій Ткаченко",
            "guest_count": 4,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.PENDING,
            "notes": "Потрібен високий стільчик",
        },
        # ── Past reservation ──
        {
            "table": "T3",
            "customer_name": "Наталія Попова",
            "guest_count": 6,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.COMPLETED,
            "notes": "День народження",
        },
        # ── Cancelled reservation ──
        {
            "table": "T2",
            "customer_name": "Тетяна Савченко",
            "guest_count": 4,
            "start_at": None,
            "end_at": None,
            "type": ReservationType.PRE_BOOKED,
            "status": ReservationStatus.CANCELLED,
            "notes": "Захворіли",
        },
    ],
}


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
                dict(r) for r in _RESERVATIONS.get(restaurant.name, [])
            ]

            status_counters = defaultdict(count)
            for data in reservations_config:
                i = next(status_counters[data["status"]])
                match data["status"]:
                    case ReservationStatus.ACTIVE:
                        data["start_at"] = now - timedelta(hours=1) + timedelta(minutes=i * 12)
                        data["end_at"] = data["start_at"] + timedelta(hours=2, minutes=30)
                    case ReservationStatus.PENDING:
                        data["start_at"] = now + timedelta(minutes=i * 10 + 15)
                        data["end_at"] = data["start_at"] + timedelta(hours=2)
                    case ReservationStatus.COMPLETED:
                        data["start_at"] = now - timedelta(days=i + 1)
                        data["end_at"] = data["start_at"] + timedelta(hours=2)
                    case ReservationStatus.CANCELLED:
                        data["start_at"] = now + timedelta(days=i + 2)
                        data["end_at"] = data["start_at"] + timedelta(hours=2)

            for data in reservations_config:
                table = tables_by_number.get(data["table"])
                if table is None:
                    continue

                reservation, was_created = Reservation.objects.get_or_create(
                    restaurant=restaurant,
                    table=table,
                    start_at=data["start_at"],
                    defaults={
                        "guest_name": data["customer_name"],
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
                            ends_at=reservation.end_at,
                        )

        self.stdout.write(self.style.SUCCESS(f"Done: {created_reservations} reservations created"))
