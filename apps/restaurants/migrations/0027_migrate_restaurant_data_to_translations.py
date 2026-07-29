from typing import Any

from django.db import migrations


def migrate_addresses(apps: Any, schema_editor: Any) -> None:
    Restaurant = apps.get_model("restaurants", "Restaurant")
    RestaurantTranslation = apps.get_model("restaurants", "RestaurantTranslation")
    RestaurantSettings = apps.get_model("restaurants", "RestaurantSettings")

    settings_map = {}
    for rs in RestaurantSettings.objects.all():
        settings_map[rs.restaurant_id] = rs

    for restaurant in Restaurant.objects.all():
        locale = "en"
        rs = settings_map.get(restaurant.pk)
        if rs:
            locale = rs.locale
        RestaurantTranslation.objects.get_or_create(
            restaurant=restaurant,
            language_code=locale,
            defaults={"address": restaurant.address},
        )


def reverse_migration(apps: Any, schema_editor: Any) -> None:
    RestaurantTranslation = apps.get_model("restaurants", "RestaurantTranslation")
    RestaurantTranslation.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("restaurants", "0026_create_restaurant_translation"),
    ]

    operations = [
        migrations.RunPython(migrate_addresses, reverse_migration),
    ]
