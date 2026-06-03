from typing import Any

from django.core.management.base import BaseCommand

from apps.authentication.models import RoleCode, User


class Command(BaseCommand):
    help = "Seed a default superuser for Django admin access"

    def handle(self, *args: Any, **options: Any) -> None:
        email = "admin@tablemate.com"
        password = "admin123"

        if User.objects.filter(email=email).exists():
            self.stdout.write(f"Superuser {email} already exists — skipping.")
            return

        User.objects.create_superuser(
            email=email,
            password=password,
            first_name="Admin",
            last_name="TableMate",
            role=RoleCode.ADMIN,
        )
        self.stdout.write(self.style.SUCCESS(f"Superuser created: {email} / {password}"))
