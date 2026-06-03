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
        seed_kwargs: dict[str, Any] = {}
        if options.get("restaurant_id"):
            seed_kwargs["restaurant_id"] = options["restaurant_id"]

        self.stdout.write("=== Seeding superuser ===")
        call_command("seed_superuser")

        self.stdout.write("\n=== Seeding restaurants ===")
        call_command("seed_restaurants", **seed_kwargs)

        self.stdout.write("\n=== Seeding menu ===")
        call_command("seed_menu", **seed_kwargs)

        self.stdout.write("\n=== Seeding users ===")
        call_command("seed_users", **seed_kwargs)

        self.stdout.write("\n=== Seeding receipts ===")
        call_command("seed_receipts")

        self.stdout.write("\n=== Seeding reservations ===")
        call_command("seed_reservations", **seed_kwargs)

        self.stdout.write(self.style.SUCCESS("\n✓ Database seeding complete"))
