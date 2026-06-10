from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.authentication.models import RoleCode, User
from apps.restaurants.models import Restaurant


class Command(BaseCommand):
    help = "Seed a waiter user linked to a restaurant"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--restaurant-id",
            type=int,
            help="Internal restaurant ID to assign the waiter to (seeds all if omitted)",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        restaurant_id = options.get("restaurant_id")
        restaurants = Restaurant.objects.all()
        if restaurant_id:
            restaurants = restaurants.filter(pk=restaurant_id)

        for restaurant in restaurants:
            email = f"waiter@{restaurant.name.lower().replace(' ', '')}.com"
            password = "waiter123"

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
                self.stdout.write(f"Waiter {email} already exists — skipping.")
