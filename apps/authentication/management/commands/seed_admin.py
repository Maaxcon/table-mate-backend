from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.authentication.models import RoleCode, User
from apps.restaurants.models import Restaurant


def _default_admin_email(restaurant_name: str) -> str:
    name_slug = restaurant_name.lower().replace(" ", "")
    return f"admin@{name_slug}.com"


class Command(BaseCommand):
    help = "Seed an admin user linked to a restaurant"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--restaurant-id",
            type=int,
            help="Internal restaurant ID to assign the admin to (seeds all if omitted)",
        )
        parser.add_argument(
            "--email",
            type=str,
            help="Override admin email for all seeded restaurants",
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
            email = override_email or _default_admin_email(restaurant.name)

            password = "admin123"  # nosec B105

            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": "Admin",
                    "last_name": restaurant.name,
                    "role": RoleCode.ADMIN,
                    "restaurant": restaurant,
                    "is_staff": True,
                    "is_superuser": True,
                },
            )

            if created:
                user.set_password(password)
                user.save(update_fields=["password"])
                self.stdout.write(self.style.SUCCESS(f"Admin created: {email} / {password}"))
            else:
                if user.restaurant_id != restaurant.pk or user.role != RoleCode.ADMIN:
                    user.restaurant = restaurant
                    user.role = RoleCode.ADMIN
                    user.is_staff = True
                    user.is_superuser = True
                    user.save(update_fields=["restaurant", "role", "is_staff", "is_superuser"])
                    self.stdout.write(self.style.SUCCESS(f"Admin {email} reassigned to {restaurant.name}"))
                else:
                    self.stdout.write(f"Admin {email} already exists — skipping.")
