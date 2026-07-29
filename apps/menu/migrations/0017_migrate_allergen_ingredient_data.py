from collections import defaultdict

from django.db import migrations

from ..allergens import ALLERGEN_KEYS, ALLERGEN_LABELS


def seed_allergens(apps, schema_editor):
    Allergen = apps.get_model("menu", "Allergen")
    AllergenTranslation = apps.get_model("menu", "AllergenTranslation")
    for sort_order, key in enumerate(ALLERGEN_KEYS):
        allergen = Allergen.objects.create(key=key, sort_order=sort_order)
        for lang_code, label in ALLERGEN_LABELS[key].items():
            AllergenTranslation.objects.create(
                allergen=allergen,
                language_code=lang_code,
                name=label,
            )


def migrate_allergen_data(apps, schema_editor):
    MenuItem = apps.get_model("menu", "MenuItem")
    Allergen = apps.get_model("menu", "Allergen")
    MenuItemAllergen = apps.get_model("menu", "MenuItemAllergen")
    allergen_map = {a.key: a for a in Allergen.objects.all()}
    for item in MenuItem.objects.all():
        stored = item.allergens or []
        if not isinstance(stored, list):
            stored = []
        allergen_keys = [a for a in stored if a in allergen_map]
        sort_order = 0
        for key in allergen_keys:
            MenuItemAllergen.objects.create(
                menu_item=item,
                allergen=allergen_map[key],
                sort_order=sort_order,
            )
            sort_order += 1


def migrate_ingredient_data(apps, schema_editor):
    MenuItem = apps.get_model("menu", "MenuItem")
    Ingredient = apps.get_model("menu", "Ingredient")
    IngredientTranslation = apps.get_model("menu", "IngredientTranslation")
    MenuItemIngredient = apps.get_model("menu", "MenuItemIngredient")
    MenuItemTranslation = apps.get_model("menu", "MenuItemTranslation")

    for item in MenuItem.objects.all():
        stored = item.ingredients or []
        if not isinstance(stored, list):
            stored = []
        for sort_order, name in enumerate(stored):
            key = _slugify(name)
            ingredient, _ = Ingredient.objects.get_or_create(
                restaurant=item.restaurant,
                key=key,
                defaults={"sort_order": sort_order},
            )
            IngredientTranslation.objects.get_or_create(
                ingredient=ingredient,
                language_code="uk",
                defaults={"name": name},
            )
            MenuItemIngredient.objects.create(
                menu_item=item,
                ingredient=ingredient,
                sort_order=sort_order,
            )

    for mit in MenuItemTranslation.objects.all():
        stored = mit.ingredients or []
        if not isinstance(stored, list):
            continue
        for sort_order, name in enumerate(stored):
            key = _slugify(name)
            ingredient = Ingredient.objects.filter(
                restaurant=mit.menu_item.restaurant,
                key=key,
            ).first()
            if ingredient:
                IngredientTranslation.objects.get_or_create(
                    ingredient=ingredient,
                    language_code=mit.language_code,
                    defaults={"name": name},
                )


def _slugify(value):
    import re
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9а-яіїєґ'\u0301]+", "-", value)
    value = value.strip("-")
    return value[:100] or "ingredient"


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0016_create_allergen_ingredient_tables"),
    ]

    operations = [
        migrations.RunPython(seed_allergens, migrations.RunPython.noop),
        migrations.RunPython(migrate_allergen_data, migrations.RunPython.noop),
        migrations.RunPython(migrate_ingredient_data, migrations.RunPython.noop),
    ]
