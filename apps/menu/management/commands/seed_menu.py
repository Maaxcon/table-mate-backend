from decimal import Decimal
from typing import Any, TypedDict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.menu.models import Menu, MenuCategory, MenuItem
from apps.restaurants.models import Restaurant

_MenuItem = tuple[str, str, Decimal, bool]


class _MenuCategory(TypedDict):
    sort_order: int
    items: list[_MenuItem]


class _Menu(TypedDict):
    is_active: bool
    categories: dict[str, _MenuCategory]


_MENUS_DATA: dict[str, _Menu] = {
    "Обіднє меню": {
        "is_active": True,
        "categories": {
            "Салати": {
                "sort_order": 1,
                "items": [
                    (
                        "Цезар з куркою",
                        "Класичний салат з курячим філе, пармезаном та грінками",
                        Decimal("195.0000"),
                        True,
                    ),
                    ("Грецький салат", "Свіжі овочі з фетою та оливковою олією", Decimal("165.0000"), True),
                    ("Теплий салат з лососем", "Лосось, мікс салату, авокадо, соус териякі", Decimal("245.0000"), True),
                ],
            },
            "Супи": {
                "sort_order": 2,
                "items": [
                    ("Борщ український", "Наваристий борщ з пампушками та сметаною", Decimal("135.0000"), True),
                    ("Крем-суп грибний", "Ніжний грибний крем-суп з вершками", Decimal("125.0000"), True),
                    ("Солянка м'ясна", "Насичений суп з кількома видами м'яса", Decimal("155.0000"), True),
                ],
            },
            "Гарячі страви": {
                "sort_order": 3,
                "items": [
                    ("Котлета по-київськи", "Соковита котлета з вершковим маслом всередині", Decimal("225.0000"), True),
                    ("Стейк з яловичини", "Американський стейк з овочами гриль", Decimal("495.0000"), True),
                    ("Куряче філе на грилі", "Куряче філе з овочевим гарніром", Decimal("215.0000"), True),
                    ("Свиняча відбивна", "Соковита відбивна з картопляним пюре", Decimal("235.0000"), True),
                ],
            },
            "Гарніри": {
                "sort_order": 4,
                "items": [
                    ("Картопля фрі", "Хрустка картопля з соусом", Decimal("79.0000"), True),
                    ("Овочі гриль", "Свіжі овочі, запечені на грилі", Decimal("99.0000"), True),
                    ("Рис з овочами", "Пропарений рис з морквою та кукурудзою", Decimal("89.0000"), True),
                ],
            },
            "Напої": {
                "sort_order": 5,
                "items": [
                    ("Узвар", "Традиційний український узвар із сухофруктів", Decimal("45.0000"), True),
                    ("Компот", "Домашній компот з ягід", Decimal("45.0000"), True),
                    ("Чай чорний", "Чай з лимоном та цукром", Decimal("35.0000"), True),
                    ("Кава американо", "Американо зі свіжозмеленої кави", Decimal("55.0000"), True),
                ],
            },
            "Десерти": {
                "sort_order": 6,
                "items": [
                    ("Тірамісу", "Класичний італійський десерт з маскарпоне", Decimal("145.0000"), True),
                    ("Морозиво в асортименті", "Три кульки морозива на вибір", Decimal("95.0000"), True),
                    ("Чізкейк Нью-Йорк", "Класичний вершковий чізкейк", Decimal("165.0000"), True),
                ],
            },
        },
    },
    "Вечірнє меню": {
        "is_active": True,
        "categories": {
            "Холодні закуски": {
                "sort_order": 1,
                "items": [
                    ("Карпаччо з яловичини", "Тонко нарізана яловичина з пармезаном", Decimal("295.0000"), True),
                    ("Брускетта з томатами", "Хрусткий хліб з томатами та базиліком", Decimal("165.0000"), True),
                    ("Тартар із тунця", "Свіжий тунець з каперсами та цибулею", Decimal("345.0000"), True),
                ],
            },
            "Паста": {
                "sort_order": 2,
                "items": [
                    ("Карбонара", "Спагеті з беконом, яйцем та пармезаном", Decimal("265.0000"), True),
                    ("Равіолі з рикоттою", "Домашні равіолі з рикоттою та шпинатом", Decimal("285.0000"), True),
                    ("Лазанья болоньєзе", "Класична лазанья з м'ясним соусом", Decimal("295.0000"), True),
                ],
            },
            "Піца": {
                "sort_order": 3,
                "items": [
                    ("Маргарита", "Томатний соус, моцарела, базилік", Decimal("195.0000"), True),
                    ("Салямі", "Піца з салямі, моцарелою та томатним соусом", Decimal("225.0000"), True),
                    ("Чотири сири", "Моцарела, пармезан, горгонзола, фета", Decimal("265.0000"), True),
                    ("Прошутто е рукола", "Шинка прошутто, рукола, пармезан", Decimal("295.0000"), True),
                ],
            },
            "Риба та морепродукти": {
                "sort_order": 4,
                "items": [
                    ("Лосось з лимонним соусом", "Філе лосося з вершково-лимонним соусом", Decimal("395.0000"), True),
                    ("Креветки на грилі", "Тигрові креветки з часниковим маслом", Decimal("345.0000"), True),
                    ("Мідії у білому вині", "Мідії з часником та білим вином", Decimal("315.0000"), True),
                ],
            },
            "Вино": {
                "sort_order": 5,
                "items": [
                    ("Шардоне біле сухе", "Франція, 0.75л", Decimal("450.0000"), True),
                    ("Каберне совіньйон червоне сухе", "Чилі, 0.75л", Decimal("490.0000"), True),
                    ("Піно Гріджіо", "Італія, 0.75л", Decimal("420.0000"), True),
                ],
            },
            "Коктейлі": {
                "sort_order": 6,
                "items": [
                    ("Мохіто", "Ром, лайм, м'ята, содова", Decimal("195.0000"), True),
                    ("Лонг Айленд", "Горілка, джин, ром, текіла, кола", Decimal("225.0000"), True),
                    ("Піна Колада", "Ром, кокосове молоко, ананасовий сік", Decimal("215.0000"), True),
                ],
            },
        },
    },
    "Сезонне меню": {
        "is_active": False,
        "categories": {
            "Літні салати": {
                "sort_order": 1,
                "items": [
                    ("Салат з полуницею", "Мікс салату, полуниця, бальзаміко", Decimal("185.0000"), False),
                    ("Грецький з авокадо", "Класичний грецький з додаванням авокадо", Decimal("195.0000"), False),
                ],
            },
            "Страви з гриля": {
                "sort_order": 2,
                "items": [
                    ("Шашлик зі свинини", "Свинина, маринована з травами", Decimal("295.0000"), False),
                    ("Бараніна на грилі", "Соковита бараніна з розмарином", Decimal("395.0000"), False),
                ],
            },
        },
    },
}


class Command(BaseCommand):
    help = "Seed menu data — menus, categories, items"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--restaurant-id",
            type=int,
            help="Restaurant ID to seed (seeds all if omitted)",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        restaurants = Restaurant.objects.all()
        if options["restaurant_id"]:
            restaurants = restaurants.filter(pk=options["restaurant_id"])
        if not restaurants.exists():
            self.stdout.write(self.style.WARNING("No restaurants found. Create one first."))
            return

        created_menus = 0
        created_categories = 0
        created_items = 0

        for restaurant in restaurants:
            self.stdout.write(f"Seeding menu for restaurant: {restaurant.name}")

            for menu_name, menu_data in _MENUS_DATA.items():
                menu, was_created = Menu.objects.update_or_create(
                    restaurant=restaurant,
                    name=menu_name,
                    defaults={"is_active": menu_data["is_active"]},
                )
                if was_created:
                    created_menus += 1

                for category_name, category_data in menu_data["categories"].items():
                    category, was_created_cat = MenuCategory.objects.update_or_create(
                        menu=menu,
                        name=category_name,
                        defaults={"sort_order": category_data["sort_order"]},
                    )
                    if was_created_cat:
                        created_categories += 1

                    for item_name, description, price, is_available in category_data["items"]:
                        _, was_created_item = MenuItem.objects.update_or_create(
                            menu=menu,
                            name=item_name,
                            defaults={
                                "restaurant": restaurant,
                                "category": category,
                                "description": description,
                                "price": price,
                                "is_available": is_available,
                                "sort_order": category_data["sort_order"],
                            },
                        )
                        if was_created_item:
                            created_items += 1

        self.stdout.write(
            self.style.SUCCESS(f"Done: {created_menus} menus, {created_categories} categories, {created_items} items")
        )
