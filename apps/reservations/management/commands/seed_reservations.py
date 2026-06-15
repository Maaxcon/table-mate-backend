from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.authentication.models import RoleCode, User
from apps.orders.models import Session
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Restaurant, Table


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

            tables = list(Table.objects.filter(restaurant=restaurant, active=True))
            if not tables:
                self.stdout.write(self.style.WARNING(f"No active tables for {restaurant.name}. Skipping."))
                continue

            customers = list(User.objects.filter(restaurant=restaurant, role=RoleCode.CUSTOMER))
            if not customers:
                self.stdout.write(self.style.WARNING(f"No customer users for {restaurant.name}. Skipping."))
                continue

            # Delete all existing sessions and reservations for a clean seed
            Session.objects.filter(restaurant=restaurant).delete()
            Reservation.objects.filter(restaurant=restaurant).delete()

            reservations_config: list[dict[str, Any]] = [
                # ── Active reservations (ongoing now → sessions created → OCCUPIED) ──
                # Tables 1, 2, 3, 5
                {
                    "table": tables[0 % len(tables)],
                    "customer": customers[0 % len(customers)],
                    "guest_count": 2,
                    "start_at": now - timedelta(hours=1),
                    "end_at": now + timedelta(hours=2),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.ACTIVE,
                    "notes": "Алергія на горіхи",
                },
                {
                    "table": tables[1 % len(tables)],
                    "customer": customers[1 % len(customers)],
                    "guest_count": 4,
                    "start_at": now - timedelta(minutes=45),
                    "end_at": now + timedelta(hours=1, minutes=30),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.ACTIVE,
                    "notes": None,
                },
                {
                    "table": tables[2 % len(tables)],
                    "customer": customers[2 % len(customers)],
                    "guest_count": 3,
                    "start_at": now - timedelta(minutes=90),
                    "end_at": now + timedelta(minutes=90),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.ACTIVE,
                    "notes": "Дитячий стільчик",
                },
                {
                    "table": tables[4 % len(tables)],
                    "customer": customers[0 % len(customers)],
                    "guest_count": 5,
                    "start_at": now - timedelta(minutes=30),
                    "end_at": now + timedelta(hours=3),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.ACTIVE,
                    "notes": None,
                },
                # ── Pending reservations (upcoming soon → no sessions → RESERVED) ──
                # Tables 8, 9 (the two the user reported as broken)
                {
                    "table": tables[7 % len(tables)],
                    "customer": customers[1 % len(customers)],
                    "guest_count": 4,
                    "start_at": now + timedelta(minutes=8),
                    "end_at": now + timedelta(hours=2, minutes=30),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.PENDING,
                    "notes": "Потрібен високий стільчик",
                },
                {
                    "table": tables[8 % len(tables)],
                    "customer": customers[2 % len(customers)],
                    "guest_count": 3,
                    "start_at": now + timedelta(minutes=12),
                    "end_at": now + timedelta(hours=2),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.PENDING,
                    "notes": None,
                },
                # ── Far future pending (outside 15 min window → shows FREE) ──
                {
                    "table": tables[9 % len(tables)],
                    "customer": customers[0 % len(customers)],
                    "guest_count": 4,
                    "start_at": now + timedelta(days=2, hours=1),
                    "end_at": now + timedelta(days=2, hours=3),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.PENDING,
                    "notes": None,
                },
                # ── Past reservations (now completed, no effect on floor plan) ──
                {
                    "table": tables[3 % len(tables)],
                    "customer": customers[1 % len(customers)],
                    "guest_count": 6,
                    "start_at": now - timedelta(days=2),
                    "end_at": now - timedelta(days=2) + timedelta(hours=2),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.COMPLETED,
                    "notes": "День народження",
                },
                {
                    "table": tables[6 % len(tables)],
                    "customer": customers[0 % len(customers)],
                    "guest_count": 8,
                    "start_at": now - timedelta(days=1),
                    "end_at": now - timedelta(days=1) + timedelta(hours=2),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.COMPLETED,
                    "notes": None,
                },
                # ── Cancelled reservation ──
                {
                    "table": tables[5 % len(tables)],
                    "customer": customers[2 % len(customers)],
                    "guest_count": 4,
                    "start_at": now + timedelta(days=3),
                    "end_at": now + timedelta(days=3, hours=2),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.CANCELLED,
                    "notes": "Захворіли",
                },
                # ── Future reservation (for table 1, different slot) ──
                {
                    "table": tables[0 % len(tables)],
                    "customer": customers[2 % len(customers)],
                    "guest_count": 3,
                    "start_at": now + timedelta(days=1, hours=3),
                    "end_at": now + timedelta(days=1, hours=5),
                    "type": ReservationType.PRE_BOOKED,
                    "status": ReservationStatus.ACTIVE,
                    "notes": None,
                },
            ]

            for data in reservations_config:
                reservation, was_created = Reservation.objects.get_or_create(
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

                # Create Session for ACTIVE reservations (required for is_occupied)
                if data["status"] == ReservationStatus.ACTIVE:
                    session_exists = Session.objects.filter(reservation=reservation).exists()
                    if not session_exists:
                        staff_user = User.objects.filter(
                            restaurant=restaurant,
                            role__in=[RoleCode.WAITER, RoleCode.ADMIN],
                        ).first()
                        Session.objects.create(
                            restaurant=restaurant,
                            table=data["table"],
                            reservation=reservation,
                            opened_by=staff_user,
                            guest_count=reservation.guest_count,
                            currency="EUR",
                            opened_at=reservation.start_at,
                        )

        self.stdout.write(self.style.SUCCESS(f"Done: {created_reservations} reservations created"))
