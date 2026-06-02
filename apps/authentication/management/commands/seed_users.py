from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.authentication.models import RoleCode, User
from apps.restaurants.models import Restaurant

_CUSTOMERS_PER_RESTAURANT: list[dict[str, str]] = [
    {"email": "dmytro@example.com", "first_name": "Дмитро", "last_name": "Коваленко", "phone": "+380501234567"},
    {"email": "olena@example.com", "first_name": "Олена", "last_name": "Шевченко", "phone": "+380671234567"},
    {"email": "andriy@example.com", "first_name": "Андрій", "last_name": "Бондаренко", "phone": "+380931234567"},
    {"email": "mariana@example.com", "first_name": "Мар'яна", "last_name": "Ткаченко", "phone": "+380631234567"},
    {"email": "ivan@example.com", "first_name": "Іван", "last_name": "Кравченко", "phone": "+380991234567"},
]


class Command(BaseCommand):
    help = "Seed customer users for restaurants"

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
            self.stdout.write(self.style.WARNING("No restaurants found. Skipping user seeding."))
            return

        created_count = 0

        for restaurant in restaurants:
            self.stdout.write(f"Seeding customers for restaurant: {restaurant.name}")

            for data in _CUSTOMERS_PER_RESTAURANT:
                _, was_created = User.objects.get_or_create(
                    email=data["email"],
                    defaults={
                        "first_name": data["first_name"],
                        "last_name": data["last_name"],
                        "phone": data["phone"],
                        "role": RoleCode.CUSTOMER,
                        "restaurant": restaurant,
                    },
                )
                if was_created:
                    user = User.objects.get(email=data["email"])
                    user.set_password("password123")
                    user.save(update_fields=["password"])
                    created_count += 1

        self.stdout.write(self.style.SUCCESS(f"Done: {created_count} customer users created (password: password123)"))
