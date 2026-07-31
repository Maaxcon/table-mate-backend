from django.db import migrations

_COVER_IMAGE = "restaurants/covers/meat-for-dinner-58560528930986.png"

_ADMIN_EMAILS = [
    "gnennijo@gmail.com",
    "gakhovalera2004@gmail.com",
    "kurilchuk.maksk2005@gmail.com",
]

_IMAGE_MAP: dict[str, str] = {
    "Цезар з куркою": "menu_items/unitable-224_RFW6Ep0.jpg",
    "Грецький салат": "menu_items/unitable-225.jpg",
    "Теплий салат із картоплі з лососем і шпинатом": "menu_items/unitable-226.jpg",
    "Борщ український": "menu_items/unitable-227.jpg",
    "Крем-суп грибний": "menu_items/unitable-228.jpg",
    "Солянка м'ясна": "menu_items/unitable-229.jpg",
    "Котлета по-київськи": "menu_items/unitable-230_Qvri0f6.jpg",
    "Стейк з яловичини": "menu_items/unitable-231_2SycXsc.jpg",
    "Куряче філе на грилі": "menu_items/unitable-232.jpg",
    "Свиняча відбивна": "menu_items/unitable-233.jpg",
    "Картопля фрі": "menu_items/unitable-234_GRS2sGp.jpg",
    "Овочі гриль": "menu_items/unitable-235.jpg",
    "Рис з овочами": "menu_items/unitable-236_wm17Jzw.jpg",
    "Узвар": "menu_items/unitable-237.jpg",
    "Компот": "menu_items/unitable-238.jpg",
    "Чай чорний": "menu_items/unitable-239.jpg",
    "Кава американо": "menu_items/unitable-240_2k2NLJR.jpg",
    "Тірамісу": "menu_items/unitable-241_dFDFKeF.jpg",
    "Морозиво в асортименті": "menu_items/unitable-242_7UH8Zq5.jpg",
    "Чізкейк Нью-Йорк": "menu_items/unitable-243.jpg",
    "Карпаччо з яловичини": "menu_items/unitable-244_wtRc5aJ.jpg",
    "Брускетта з томатами": "menu_items/unitable-245_HugsS86.jpg",
    "Тартар із тунця": "menu_items/unitable-246.jpg",
    "Карбонара": "menu_items/unitable-247.jpg",
    "Равіолі з рикоттою": "menu_items/unitable-248.jpg",
    "Лазанья болоньєзе": "menu_items/unitable-249.jpg",
    "Маргарита": "menu_items/unitable-250.jpg",
    "Салямі": "menu_items/unitable-251.jpg",
    "Чотири сири": "menu_items/unitable-252.jpg",
    "Прошутто е рукола": "menu_items/unitable-253_PrMJnh8.jpg",
    "Лосось з лимонним соусом": "menu_items/unitable-254.jpg",
    "Креветки на грилі": "menu_items/unitable-255.jpg",
    "Мідії у білому вині": "menu_items/unitable-256.jpg",
    "Шардоне біле сухе": "menu_items/unitable-257_xqqVaT9.jpg",
    "Каберне совіньйон червоне сухе": "menu_items/unitable-258_hwLoVvS.jpg",
    "Піно Гріджіо": "menu_items/unitable-259.jpg",
    "Мохіто": "menu_items/unitable-260.jpg",
    "Лонг Айленд": "menu_items/unitable-261.jpg",
    "Піна Колада": "menu_items/unitable-262.jpg",
    "Салат з полуницею": "menu_items/unitable-263_bvUNcSY.jpg",
    "Грецький з авокадо": "menu_items/unitable-264_ss4L1u3.jpg",
    "Шашлик зі свинини": "menu_items/unitable-265_1tUIOCI.jpg",
    "Бараніна на грилі": "menu_items/unitable-266.jpg",
}


def seed_unitable(apps: object, schema_editor: object) -> None:
    # Uses live models/commands (not the historical `apps` registry) because
    # seed_restaurants/seed_layouts/seed_menu depend on model behavior
    # (public_id generation, RestaurantScopedModel save logic) that frozen
    # historical models don't have. Keep this migration last in restaurants/
    # menu/editor's dependency chain if those models change shape later.
    from django.core.management import call_command

    from apps.authentication.models import RoleCode, User
    from apps.menu.models import MenuItem
    from apps.restaurants.models import Restaurant

    call_command("seed_restaurants")

    unitable = Restaurant.objects.get(name="UniTable")

    call_command("seed_layouts", restaurant_id=unitable.id)
    call_command("seed_menu", restaurant_id=unitable.id)

    unitable.cover_image = _COVER_IMAGE
    unitable.save(update_fields=["cover_image"])

    terrace = Restaurant.objects.filter(name="Table Mate Terrace").first()
    if terrace:
        terrace.cover_image = _COVER_IMAGE
        terrace.save(update_fields=["cover_image"])

    for name, image in _IMAGE_MAP.items():
        MenuItem.objects.filter(restaurant=unitable, name=name).update(image=image)

    # No password is set — these admins sign in with Google, which never
    # checks the password field, so an unusable password is enough.
    for email in _ADMIN_EMAILS:
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "role": RoleCode.ADMIN,
                "restaurant": unitable,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        else:
            user.restaurant = unitable
            user.role = RoleCode.ADMIN
            user.is_staff = True
            user.is_superuser = True
            user.save(update_fields=["restaurant", "role", "is_staff", "is_superuser"])


def noop_reverse(apps: object, schema_editor: object) -> None:
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("restaurants", "0021_zone_canvas_dimensions"),
        ("menu", "0012_menucategory_color"),
        ("editor", "0005_layoutversion_immutable_trigger"),
        ("authentication", "0007_alter_user_email"),
    ]

    # seed_unitable is intentionally NOT run here: its live-model commands
    # (seed_restaurants/seed_layouts/seed_menu) require a fully migrated schema
    # (e.g. restaurantsettings.supported_languages, added in 0024/0025). The
    # RunPython moved to 0030_seed_unitable_prod_data at the tail of the
    # restaurants dependency chain. This migration is kept as a no-op so the
    # already-applied record stays valid and fresh DBs skip the early seed.
    operations = [
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
    ]
