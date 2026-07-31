from typing import Any

import django.db.models.deletion
from django.db import migrations, models

from ..allergens import ALLERGEN_KEYS, ALLERGEN_LABELS




def seed_and_scope_allergens(apps: Any, schema_editor: Any) -> None:
    """Seed the standard 14 allergens per restaurant, backfill ``name`` from the
    locale-matching translation, remap junction rows to per-restaurant copies, and
    delete the now-unreferenced global rows (FR-015 / plan Phase 2)."""
    Allergen = apps.get_model("menu", "Allergen")
    AllergenTranslation = apps.get_model("menu", "AllergenTranslation")
    MenuItemAllergen = apps.get_model("menu", "MenuItemAllergen")
    Restaurant = apps.get_model("restaurants", "Restaurant")
    RestaurantSettings = apps.get_model("restaurants", "RestaurantSettings")

    locales: dict[int, str] = {rs.restaurant_id: rs.locale for rs in RestaurantSettings.objects.all()}

    def locale_for(restaurant_id: int) -> str:
        return locales.get(restaurant_id, "en")

    global_rows = list(Allergen.objects.filter(restaurant__isnull=True))
    globals_by_key: dict[str, list[Any]] = {}
    for a in global_rows:
        globals_by_key.setdefault(a.key, []).append(a)

    scoped: dict[tuple[int, str], Any] = {}

    # 1. Seed the standard 14 allergens per restaurant from the canonical labels,
    #    with the restaurant's default-locale label stored as ``name`` and the
    #    remaining label languages kept as translations (FR-015).
    for restaurant in Restaurant.objects.all():
        locale = locale_for(restaurant.pk)
        for sort_order, key in enumerate(ALLERGEN_KEYS):
            label = ALLERGEN_LABELS.get(key, {})
            name = label.get(locale) or label.get("en") or key
            allergen = Allergen.objects.create(
                restaurant_id=restaurant.pk,
                key=key,
                name=name,
                sort_order=sort_order,
            )
            scoped[(restaurant.pk, key)] = allergen
            for lang_code, lang_name in label.items():
                if lang_code != locale:
                    AllergenTranslation.objects.create(
                        allergen=allergen,
                        language_code=lang_code,
                        name=lang_name,
                    )

    # 2. Carry over non-default-language translations from the global rows to the
    #    per-restaurant copies so localization survives the remap.
    for key, globals_ in globals_by_key.items():
        for global_a in globals_:
            for t in global_a.translations.all():
                for (restaurant_id, scoped_key), scoped_a in scoped.items():
                    if scoped_key != key:
                        continue
                    if t.language_code == locale_for(restaurant_id):
                        continue
                    AllergenTranslation.objects.get_or_create(
                        allergen=scoped_a,
                        language_code=t.language_code,
                        defaults={"name": t.name},
                    )

    # 3. Remap junction rows to the per-restaurant copies. Custom keys (created by
    #    admins) get a copy backfilled from their global translations.
    for mia in MenuItemAllergen.objects.select_related("menu_item", "allergen").all():
        restaurant_id = mia.menu_item.restaurant_id
        key = mia.allergen.key
        target = scoped.get((restaurant_id, key))
        if target is None:
            locale = locale_for(restaurant_id)
            resolved_name: str | None = None
            for t in mia.allergen.translations.all():
                if t.language_code == locale:
                    resolved_name = t.name
                    break
            if resolved_name is None:
                t = mia.allergen.translations.first()
                resolved_name = t.name if t else mia.allergen.key
            target = Allergen.objects.create(
                restaurant_id=restaurant_id,
                key=key,
                name=resolved_name,
                sort_order=mia.allergen.sort_order,
            )
            for t in mia.allergen.translations.all():
                if t.language_code != locale:
                    AllergenTranslation.objects.create(
                        allergen=target,
                        language_code=t.language_code,
                        name=t.name,
                    )
            scoped[(restaurant_id, key)] = target
        if mia.allergen_id != target.pk:
            mia.allergen_id = target.pk
            mia.save(update_fields=["allergen"])

    # 4. Delete the now-unreferenced global rows (their translations cascade).
    Allergen.objects.filter(restaurant__isnull=True).delete()


def backfill_ingredient_names(apps: Any, schema_editor: Any) -> None:
    """Backfill ``Ingredient.name`` from the locale-matching translation (fallback:
    any available translation, then the key) and drop default-locale translation rows."""
    Ingredient = apps.get_model("menu", "Ingredient")
    IngredientTranslation = apps.get_model("menu", "IngredientTranslation")
    RestaurantSettings = apps.get_model("restaurants", "RestaurantSettings")

    locales = {rs.restaurant_id: rs.locale for rs in RestaurantSettings.objects.all()}

    for ingredient in Ingredient.objects.all():
        locale = locales.get(ingredient.restaurant_id, "en")
        by_code = {t.language_code: t.name for t in ingredient.translations.all()}
        name = by_code.get(locale) or next(iter(by_code.values()), None) or ingredient.key
        ingredient.name = name
        ingredient.save(update_fields=["name"])
        IngredientTranslation.objects.filter(
            ingredient_id=ingredient.id,
            language_code=locale,
        ).delete()

class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0023_allergen_ingredient_scoping_schema"),
    ]

    operations = [
        migrations.RunPython(seed_and_scope_allergens, migrations.RunPython.noop),
        migrations.RunPython(backfill_ingredient_names, migrations.RunPython.noop),
    ]