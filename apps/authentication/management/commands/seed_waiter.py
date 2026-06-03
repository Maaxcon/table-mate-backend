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
            required=True,
            help="Internal restaurant ID to assign the waiter to",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        restaurant_id = options["restaurant_id"]

        try:
            restaurant = Restaurant.objects.get(pk=restaurant_id)
        except Restaurant.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Restaurant with id={restaurant_id} not found."))
            return

        email = f"waiter@{restaurant.name.lower().replace(' ', '')}.com"
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
            self.stdout.write(f"Waiter {email} already exists — skipping.")
