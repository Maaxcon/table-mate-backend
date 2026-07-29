from typing import Any

from django.db import migrations

EN_ADDRESSES: dict[str, str] = {
    "UniTable": "17 Sichovyi Lane, Cherkasy, 18015",
    "Table Mate Terrace": "12 Mykhailivska Street, Kyiv, 01001",
    "Смак Дому": "22 Khreshchatyk Street, Kyiv, 01001",
    "Барва": "45 Peremohy Avenue, Kyiv, 03150",
    "Козацький Двір": "31 Soborna Street, Odesa, 65000",
    "Море Смаку": "7 Rybalska Embankment, Kharkiv, 61000",
    "Вогнище": "10 Derybasivska Street, Odesa, 65000",
}


def seed_en_addresses(apps: Any, schema_editor: Any) -> None:
    Restaurant = apps.get_model("restaurants", "Restaurant")
    RestaurantTranslation = apps.get_model("restaurants", "RestaurantTranslation")

    for restaurant in Restaurant.objects.all():
        en_address = EN_ADDRESSES.get(restaurant.name)
        if en_address:
            RestaurantTranslation.objects.update_or_create(
                restaurant=restaurant,
                language_code="en",
                defaults={"address": en_address},
            )


def reverse_migration(apps: Any, schema_editor: Any) -> None:
    RestaurantTranslation = apps.get_model("restaurants", "RestaurantTranslation")
    restaurant_names = list(EN_ADDRESSES)
    RestaurantTranslation.objects.filter(
        restaurant__name__in=restaurant_names,
        language_code="en",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("restaurants", "0027_migrate_restaurant_data_to_translations"),
    ]

    operations = [
        migrations.RunPython(seed_en_addresses, reverse_migration),
    ]
