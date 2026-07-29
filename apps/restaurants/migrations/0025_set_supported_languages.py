from typing import Any

from django.db import migrations


def set_supported_languages(apps: Any, schema_editor: Any) -> None:
    RestaurantSettings = apps.get_model("restaurants", "RestaurantSettings")
    RestaurantSettings.objects.update(supported_languages=["uk", "en"])


def reverse_migration(apps: Any, schema_editor: Any) -> None:
    RestaurantSettings = apps.get_model("restaurants", "RestaurantSettings")
    RestaurantSettings.objects.update(supported_languages=[])


class Migration(migrations.Migration):
    dependencies = [
        ("restaurants", "0024_restaurantsettings_supported_languages"),
    ]

    operations = [
        migrations.RunPython(set_supported_languages, reverse_migration),
    ]
