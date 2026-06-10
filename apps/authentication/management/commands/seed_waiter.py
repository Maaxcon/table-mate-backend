from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.authentication.models import RoleCode, User
from apps.restaurants.models import Restaurant

_OVERRIDE_EMAILS: dict[str, str] = {
    "Table Mate": "gakhovalera2004@gmail.com",
}


def _resolve_waiter_email(restaurant_name: str, override: str | None) -> str:
    if override:
        return override
    result = _OVERRIDE_EMAILS.get(restaurant_name)
    if result is not None:
        return result
    name_slug = restaurant_name.lower().replace(" ", "")
    return f"waiter@{name_slug}.com"


class Command(BaseCommand):
    help = "Seed a waiter user linked to a restaurant"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--restaurant-id",
            type=int,
            help="Internal restaurant ID to assign the waiter to (seeds all if omitted)",
        )
        parser.add_argument(
            "--email",
            type=str,
            help="Override waiter email for all seeded restaurants",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        restaurant_id = options.get("restaurant_id")
        override_email: str | None = options.get("email")
        restaurants = Restaurant.objects.all()
        if restaurant_id:
            restaurants = restaurants.filter(pk=restaurant_id)

        if not restaurants.exists():
            raise CommandError("No restaurants found. Run seed_restaurants first.")

        for restaurant in restaurants:
            email = _resolve_waiter_email(restaurant.name, override_email)

            password = "waiter123"  # nosec B105

            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": "Waiter",
                    "last_name": restaurant.name,
                    "role": RoleCode.WAITER,
                    "restaurant": restaurant,
                    "is_staff": True,
                },
            )

            if created:
                user.set_password(password)
                user.save(update_fields=["password"])
                self.stdout.write(self.style.SUCCESS(f"Waiter created: {email} / {password}"))
            else:
                if user.restaurant_id != restaurant.pk:
                    user.restaurant = restaurant
                    user.role = RoleCode.WAITER
                    user.is_staff = True
                    user.save(update_fields=["restaurant", "role", "is_staff"])
                    self.stdout.write(self.style.SUCCESS(f"Waiter {email} reassigned to {restaurant.name}"))
                else:
                    self.stdout.write(f"Waiter {email} already exists — skipping.")
