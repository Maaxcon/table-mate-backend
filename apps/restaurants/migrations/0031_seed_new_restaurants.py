from importlib import import_module

from django.db import migrations


def _seed_new_restaurants(apps: object, schema_editor: object) -> None:
    module = import_module("apps.restaurants.migrations.0023_seed_new_restaurants")
    module.seed_new_restaurants(apps, schema_editor)


def noop_reverse(apps: object, schema_editor: object) -> None:
    pass


class Migration(migrations.Migration):
    # Runs the new-restaurants seed (previously inside 0023_seed_new_restaurants)
    # only after the full schema exists — same rationale as 0030_seed_unitable_prod_data.
    dependencies = [
        ("restaurants", "0030_seed_unitable_prod_data"),
    ]

    operations = [
        migrations.RunPython(_seed_new_restaurants, noop_reverse),
    ]
