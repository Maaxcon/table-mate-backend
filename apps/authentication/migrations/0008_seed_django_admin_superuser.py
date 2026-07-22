from typing import Any

from django.contrib.auth.hashers import make_password
from django.db import migrations
from django.db.migrations.state import StateApps

ADMIN_EMAIL = "admin@tablemate.com"
ADMIN_PASSWORD = "admin123"  # nosec B105


def seed_superuser(apps: StateApps, schema_editor: Any) -> None:
    User = apps.get_model("authentication", "User")
    User.objects.update_or_create(
        email=ADMIN_EMAIL,
        defaults={
            "first_name": "Admin",
            "last_name": "TableMate",
            "role": "admin",
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
            "password": make_password(ADMIN_PASSWORD),
        },
    )


def unseed_superuser(apps: StateApps, schema_editor: Any) -> None:
    User = apps.get_model("authentication", "User")
    User.objects.filter(email=ADMIN_EMAIL).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("authentication", "0007_alter_user_email"),
    ]

    operations = [
        migrations.RunPython(seed_superuser, unseed_superuser),
    ]
