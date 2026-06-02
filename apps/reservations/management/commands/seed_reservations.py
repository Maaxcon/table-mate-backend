from datetime import datetime, timedelta
from typing import Any, TypedDict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.authentication.models import RoleCode, User
from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import Restaurant, Table


class _ReservationData(TypedDict):
    customer: User | None
    table: Table | None
    guest_count: int
    start_at: datetime
    end_at: datetime
    status: str
    notes: str | None


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

        for restaurant in restaurants:
            self.stdout.write(f"Seeding reservations for restaurant: {restaurant.name}")

            tables = list(Table.objects.filter(restaurant=restaurant, active=True))
            if not tables:
                self.stdout.write(self.style.WARNING(f"No active tables for {restaurant.name}. Skipping."))
                continue

            customers = list(User.objects.filter(restaurant=restaurant, role=RoleCode.CUSTOMER))
            if not customers:
                self.stdout.write(self.style.WARNING(f"No customer users for {restaurant.name}. Skipping."))
                continue

            now = timezone.now()
            today_noon = now.replace(hour=12, minute=0, second=0, microsecond=0)

            reservations_data: list[_ReservationData] = [
                {
                    "customer": customers[0],
                    "table": tables[0],
                    "guest_count": 2,
                    "start_at": today_noon + timedelta(hours=1),
                    "end_at": today_noon + timedelta(hours=2, minutes=30),
                    "status": ReservationStatus.ACTIVE,
                    "notes": "Алергія на горіхи",
                },
                {
                    "customer": customers[1 % len(customers)],
                    "table": tables[1 % len(tables)],
                    "guest_count": 4,
                    "start_at": today_noon + timedelta(hours=2),
                    "end_at": today_noon + timedelta(hours=3, minutes=30),
                    "status": ReservationStatus.ACTIVE,
                    "notes": None,
                },
                {
                    "customer": customers[2 % len(customers)],
                    "table": tables[2 % len(tables)],
                    "guest_count": 3,
                    "start_at": today_noon + timedelta(hours=3),
                    "end_at": today_noon + timedelta(hours=4),
                    "status": ReservationStatus.ACTIVE,
                    "notes": "Дитячий стільчик",
                },
                {
                    "customer": customers[0],
                    "table": tables[3 % len(tables)],
                    "guest_count": 6,
                    "start_at": today_noon + timedelta(days=1, hours=0),
                    "end_at": today_noon + timedelta(days=1, hours=2),
                    "status": ReservationStatus.ACTIVE,
                    "notes": "День народження",
                },
                {
                    "customer": customers[1 % len(customers)],
                    "table": tables[4 % len(tables)],
                    "guest_count": 2,
                    "start_at": today_noon + timedelta(days=1, hours=3),
                    "end_at": today_noon + timedelta(days=1, hours=4, minutes=30),
                    "status": ReservationStatus.ACTIVE,
                    "notes": None,
                },
                {
                    "customer": customers[0],
                    "table": tables[5 % len(tables)],
                    "guest_count": 5,
                    "start_at": today_noon - timedelta(days=2, hours=1),
                    "end_at": today_noon - timedelta(days=2),
                    "status": ReservationStatus.ACTIVE,
                    "notes": "Все сподобалось",
                },
                {
                    "customer": customers[2 % len(customers)],
                    "table": tables[6 % len(tables)],
                    "guest_count": 8,
                    "start_at": today_noon - timedelta(days=1, hours=2),
                    "end_at": today_noon - timedelta(days=1),
                    "status": ReservationStatus.ACTIVE,
                    "notes": None,
                },
                {
                    "customer": customers[1 % len(customers)],
                    "table": tables[7 % len(tables)],
                    "guest_count": 4,
                    "start_at": today_noon - timedelta(days=3),
                    "end_at": today_noon - timedelta(days=3, hours=-1, minutes=30),
                    "status": ReservationStatus.CANCELLED,
                    "notes": "Захворіли",
                },
                {
                    "customer": customers[0],
                    "table": tables[0],
                    "guest_count": 2,
                    "start_at": today_noon + timedelta(days=2, hours=1),
                    "end_at": today_noon + timedelta(days=2, hours=2, minutes=30),
                    "status": ReservationStatus.ACTIVE,
                    "notes": "Веганське меню",
                },
                {
                    "customer": customers[2 % len(customers)],
                    "table": tables[2 % len(tables)],
                    "guest_count": 3,
                    "start_at": today_noon + timedelta(days=2, hours=3),
                    "end_at": today_noon + timedelta(days=2, hours=4),
                    "status": ReservationStatus.ACTIVE,
                    "notes": None,
                },
            ]

            for data in reservations_data:
                _, was_created = Reservation.objects.get_or_create(
                    restaurant=restaurant,
                    table=data["table"],
                    start_at=data["start_at"],
                    defaults={
                        "customer": data["customer"],
                        "guest_count": data["guest_count"],
                        "end_at": data["end_at"],
                        "status": data["status"],
                        "notes": data["notes"],
                    },
                )
                if was_created:
                    created_reservations += 1

        self.stdout.write(self.style.SUCCESS(f"Done: {created_reservations} reservations created"))
