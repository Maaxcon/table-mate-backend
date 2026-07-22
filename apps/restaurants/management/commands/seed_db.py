from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand

_DEFAULT_COVER = "restaurants/covers/meat-for-dinner-58560528930986.png"

_COVER_BY_NAME: dict[str, str] = {
    "UniTable": _DEFAULT_COVER,
    "Table Mate Terrace": _DEFAULT_COVER,
    "Смак Дому": "menu_items/unitable-227.jpg",
    "Барва": "menu_items/unitable-241_dFDFKeF.jpg",
    "Козацький Двір": "menu_items/unitable-265_1tUIOCI.jpg",
    "Море Смаку": "menu_items/unitable-254.jpg",
    "Вогнище": "menu_items/unitable-231_2SycXsc.jpg",
}


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

        self._assign_covers(restaurant_id)

        self.stdout.write(self.style.SUCCESS("\n✓ Database seeding complete"))

    def _assign_covers(self, restaurant_id: int | None) -> None:
        from apps.restaurants.models import Restaurant

        self.stdout.write("\n=== Assigning cover images ===")
        restaurants = Restaurant.objects.all()
        if restaurant_id:
            restaurants = restaurants.filter(pk=restaurant_id)
        updated = 0
        for r in restaurants:
            cover = _COVER_BY_NAME.get(r.name, _DEFAULT_COVER)
            if r.cover_image != cover:
                r.cover_image = cover
                r.save(update_fields=["cover_image", "updated_at"])
                updated += 1
                self.stdout.write(f"  Set cover for '{r.name}'.")
        self.stdout.write(f"  {updated} restaurant(s) updated with cover image.")
