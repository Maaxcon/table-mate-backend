from importlib import import_module

from django.db import migrations


def _seed_unitable(apps: object, schema_editor: object) -> None:
    module = import_module("apps.restaurants.migrations.0022_seed_unitable_prod_data")
    module.seed_unitable(apps, schema_editor)


def noop_reverse(apps: object, schema_editor: object) -> None:
    pass


class Migration(migrations.Migration):
    # Runs the UniTable seed (previously inside 0022_seed_unitable_prod_data)
    # only after the full schema exists: the live-model seed commands
    # (seed_restaurants/seed_layouts/seed_menu) require e.g.
    # restaurantsettings.supported_languages (0025) and the latest menu/editor
    # columns. Keep this at the tail of the restaurants dependency chain.
    dependencies = [
        ("restaurants", "0029_tabletranslation_zonetranslation"),
        ("menu", "0025_allergen_ingredient_finalize_not_null"),
        ("editor", "0006_layoutentitytranslation"),
        ("authentication", "0008_seed_django_admin_superuser"),
    ]

    operations = [
        migrations.RunPython(_seed_unitable, noop_reverse),
    ]
