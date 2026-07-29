from typing import Any

from django.db import migrations


def migrate_to_translations(apps: Any, schema_editor: Any) -> None:
    Menu = apps.get_model("menu", "Menu")
    MenuCategory = apps.get_model("menu", "MenuCategory")
    MenuItem = apps.get_model("menu", "MenuItem")
    MenuTranslation = apps.get_model("menu", "MenuTranslation")
    MenuCategoryTranslation = apps.get_model("menu", "MenuCategoryTranslation")
    MenuItemTranslation = apps.get_model("menu", "MenuItemTranslation")
    RestaurantSettings = apps.get_model("restaurants", "RestaurantSettings")

    settings_map = {}
    for rs in RestaurantSettings.objects.all():
        settings_map[rs.restaurant_id] = rs

    for menu in Menu.objects.all():
        locale = "en"
        rs = settings_map.get(menu.restaurant_id)
        if rs:
            locale = rs.locale
        if not MenuTranslation.objects.filter(menu=menu, language_code=locale).exists():
            MenuTranslation.objects.create(
                menu=menu,
                language_code=locale,
                name=menu.name,
            )

    for category in MenuCategory.objects.all():
        locale = "en"
        rs = settings_map.get(category.menu.restaurant_id)
        if rs:
            locale = rs.locale
        if not MenuCategoryTranslation.objects.filter(category=category, language_code=locale).exists():
            MenuCategoryTranslation.objects.create(
                category=category,
                language_code=locale,
                name=category.name,
            )

    for item in MenuItem.objects.all():
        locale = "en"
        rs = settings_map.get(item.restaurant_id)
        if rs:
            locale = rs.locale
        if not MenuItemTranslation.objects.filter(menu_item=item, language_code=locale).exists():
            MenuItemTranslation.objects.create(
                menu_item=item,
                language_code=locale,
                name=item.name,
                description=item.description,
                ingredients=item.ingredients,
            )


def reverse_migration(apps: Any, schema_editor: Any) -> None:
    MenuTranslation = apps.get_model("menu", "MenuTranslation")
    MenuCategoryTranslation = apps.get_model("menu", "MenuCategoryTranslation")
    MenuItemTranslation = apps.get_model("menu", "MenuItemTranslation")
    MenuTranslation.objects.all().delete()
    MenuCategoryTranslation.objects.all().delete()
    MenuItemTranslation.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0013_menu_translation_tables"),
        ("restaurants", "0024_restaurantsettings_supported_languages"),
    ]

    operations = [
        migrations.RunPython(migrate_to_translations, reverse_migration),
    ]
