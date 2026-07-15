from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed all demo data: superuser, restaurants, menu, users, receipts, reservations"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--restaurant-id",
            type=int,
            help="Restaurant ID to seed (seeds all if omitted)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        restaurant_id = options.get("restaurant_id")

        self.stdout.write("=== Seeding superuser ===")
        call_command("seed_superuser")

        self.stdout.write("\n=== Seeding restaurants ===")
        # Prune so the table set always matches the canonical seed (and the layout
        # published by seed_layouts below). Without this, tables added out-of-band
        # (e.g. via the editor UI) survive as active rows that seed_layouts drops
        # from the current layout — leaving "ghost" tables that are reservable but
        # absent from the floor plan.
        call_command("seed_restaurants", restaurant_id=restaurant_id, prune=True)

        self.stdout.write("\n=== Seeding layouts ===")
        call_command("seed_layouts", restaurant_id=restaurant_id)

        self.stdout.write("\n=== Seeding menu ===")
        call_command("seed_menu", restaurant_id=restaurant_id)

        self.stdout.write("\n=== Seeding users ===")
        call_command("seed_users", restaurant_id=restaurant_id)

        self.stdout.write("\n=== Seeding waiters ===")
        call_command("seed_waiter", restaurant_id=restaurant_id)

        self.stdout.write("\n=== Seeding void reasons ===")
        call_command("seed_void_reasons")

        self.stdout.write("\n=== Seeding receipts ===")
        call_command("seed_receipts")

        self.stdout.write("\n=== Seeding reservations ===")
        call_command("seed_reservations", restaurant_id=restaurant_id)

        self.stdout.write("\n=== Seeding orders ===")
        call_command("seed_orders", restaurant_id=restaurant_id)

        self.stdout.write(self.style.SUCCESS("\n✓ Database seeding complete"))
