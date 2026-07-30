from typing import Any

from django.db import migrations


def cleanup_duplicate_translations(apps: Any, schema_editor: Any) -> None:
    RestaurantSettings = apps.get_model("restaurants", "RestaurantSettings")
    RestaurantTranslation = apps.get_model("restaurants", "RestaurantTranslation")
    ZoneTranslation = apps.get_model("restaurants", "ZoneTranslation")
    TableTranslation = apps.get_model("restaurants", "TableTranslation")
    MenuTranslation = apps.get_model("menu", "MenuTranslation")
    MenuCategoryTranslation = apps.get_model("menu", "MenuCategoryTranslation")
    MenuItemTranslation = apps.get_model("menu", "MenuItemTranslation")
    AllergenTranslation = apps.get_model("menu", "AllergenTranslation")
    IngredientTranslation = apps.get_model("menu", "IngredientTranslation")

    for settings in RestaurantSettings.objects.iterator():
        locale = settings.locale
        rid = settings.restaurant_id

        MenuTranslation.objects.filter(menu__restaurant_id=rid, language_code=locale).delete()
        MenuCategoryTranslation.objects.filter(
            category__menu__restaurant_id=rid, language_code=locale
        ).delete()
        MenuItemTranslation.objects.filter(menu_item__restaurant_id=rid, language_code=locale).delete()
        RestaurantTranslation.objects.filter(restaurant_id=rid, language_code=locale).delete()
        ZoneTranslation.objects.filter(zone__restaurant_id=rid, language_code=locale).delete()
        TableTranslation.objects.filter(table__restaurant_id=rid, language_code=locale).delete()
        IngredientTranslation.objects.filter(
            ingredient__restaurant_id=rid, language_code=locale
        ).delete()

    AllergenTranslation.objects.filter(
        language_code__in=list(
            RestaurantSettings.objects.values_list("locale", flat=True).distinct()
        )
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0019_populate_ingredient_en_translations"),
        ("restaurants", "0029_tabletranslation_zonetranslation"),
    ]

    operations = [
        migrations.RunPython(
            cleanup_duplicate_translations,
            migrations.RunPython.noop,
        ),
    ]
