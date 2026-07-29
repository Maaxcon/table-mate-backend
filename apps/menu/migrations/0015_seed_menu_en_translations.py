from typing import Any

from django.db import migrations

MENU_TRANSLATIONS: dict[str, str] = {
    "Обіднє меню": "Lunch Menu",
    "Вечірнє меню": "Evening Menu",
    "Сезонне меню": "Seasonal Menu",
}

CATEGORY_TRANSLATIONS: dict[str, str] = {
    "Салати": "Salads",
    "Супи": "Soups",
    "Гарячі страви": "Hot Dishes",
    "Гарніри": "Side Dishes",
    "Напої": "Beverages",
    "Десерти": "Desserts",
    "Холодні закуски": "Cold Appetizers",
    "Паста": "Pasta",
    "Піца": "Pizza",
    "Риба та морепродукти": "Fish & Seafood",
    "Вино": "Wine",
    "Коктейлі": "Cocktails",
    "Літні салати": "Summer Salads",
    "Страви з гриля": "Grilled Dishes",
}

_IngredientList = list[str]
_ItemData = tuple[str, str, str, _IngredientList]
_ItemMap = dict[str, tuple[str, str, _IngredientList]]

CATEGORY_ITEMS: dict[str, _ItemMap] = {
    "Салати": {
        "Цезар з куркою": (
            "Chicken Caesar",
            "Classic salad with chicken fillet, parmesan, and croutons",
            ["chicken fillet", "romaine lettuce", "parmesan", "croutons", "Caesar dressing", "lemon juice"],
        ),
        "Грецький салат": (
            "Greek Salad",
            "Fresh vegetables with feta and olive oil",
            ["cucumber", "tomatoes", "bell pepper", "red onion", "feta", "olives", "olive oil", "oregano"],
        ),
        "Теплий салат із картоплі з лососем і шпинатом": (
            "Warm Potato Salad with Salmon and Spinach",
            "Warm potatoes with salmon, spinach, and light mustard dressing",
            ["salmon fillet", "potatoes", "spinach", "olive oil", "mustard", "lemon juice", "salt", "pepper"],
        ),
    },
    "Супи": {
        "Борщ український": (
            "Ukrainian Borscht",
            "Hearty borscht with garlic pampushky and sour cream",
            ["beetroot", "cabbage", "potatoes", "carrots", "onion", "tomato paste", "beef", "sour cream", "pampushky", "garlic"],  # noqa: E501
        ),
        "Крем-суп грибний": (
            "Mushroom Cream Soup",
            "Smooth mushroom cream soup with cream",
            ["mushrooms", "onion", "garlic", "heavy cream", "butter", "chicken broth", "nutmeg"],
        ),
        "Солянка м'ясна": (
            "Meat Solyanka",
            "Rich soup with several types of meat",
            ["beef", "smoked sausage", "ham", "pickled cucumbers", "onion", "tomato paste", "capers", "olives", "lemon"],  # noqa: E501
        ),
    },
    "Гарячі страви": {
        "Котлета по-київськи": (
            "Chicken Kyiv",
            "Juicy chicken cutlet with butter inside",
            ["chicken fillet", "butter", "egg", "breadcrumbs", "herbs", "salt", "pepper"],
        ),
        "Стейк з яловичини": (
            "Beef Steak",
            "American-style steak with grilled vegetables",
            ["ribeye beef", "garlic butter", "rosemary", "thyme", "sea salt", "black pepper", "grilled vegetables"],
        ),
        "Куряче філе на грилі": (
            "Grilled Chicken Fillet",
            "Chicken fillet with vegetable side",
            ["chicken fillet", "olive oil", "lemon", "garlic", "paprika", "rosemary", "vegetables"],
        ),
        "Свиняча відбивна": (
            "Pork Chop",
            "Juicy pork chop with mashed potatoes",
            ["pork", "egg", "flour", "breadcrumbs", "garlic", "potatoes", "butter", "milk"],
        ),
    },
    "Гарніри": {
        "Картопля фрі": (
            "French Fries",
            "Crispy fries with dipping sauce",
            ["potatoes", "sunflower oil", "salt", "choice of sauce"],
        ),
        "Овочі гриль": (
            "Grilled Vegetables",
            "Fresh vegetables baked on the grill",
            ["zucchini", "bell pepper", "eggplant", "tomato", "olive oil", "Provencal herbs", "garlic"],
        ),
        "Рис з овочами": (
            "Rice with Vegetables",
            "Steamed rice with carrots and corn",
            ["steamed rice", "carrots", "corn", "peas", "butter", "salt"],
        ),
    },
    "Напої": {
        "Узвар": (
            "Uzvar",
            "Traditional Ukrainian dried fruit compote",
            ["dried fruits", "pear", "apple", "prunes", "water", "sugar"],
        ),
        "Компот": (
            "Kompot",
            "Homemade berry compote",
            ["blackcurrant", "cherry", "raspberry", "water", "sugar"],
        ),
        "Чай чорний": (
            "Black Tea",
            "Tea with lemon and sugar",
            ["black tea", "lemon", "sugar", "water"],
        ),
        "Кава американо": (
            "Americano",
            "Americano made with freshly ground coffee",
            ["arabica coffee", "water"],
        ),
    },
    "Десерти": {
        "Тірамісу": (
            "Tiramisu",
            "Classic Italian dessert with mascarpone",
            ["mascarpone", "eggs", "sugar", "ladyfingers", "espresso", "amaretto", "cocoa"],
        ),
        "Морозиво в асортименті": (
            "Ice Cream Assortment",
            "Three scoops of ice cream of your choice",
            ["milk", "cream", "sugar", "stabilizer", "choice of topping"],
        ),
        "Чізкейк Нью-Йорк": (
            "New York Cheesecake",
            "Classic creamy cheesecake",
            ["cream cheese", "cream", "eggs", "sugar", "vanilla", "shortbread cookies", "butter"],
        ),
    },
    "Холодні закуски": {
        "Карпаччо з яловичини": (
            "Beef Carpaccio",
            "Thinly sliced beef with parmesan",
            ["beef tenderloin", "parmesan", "arugula", "capers", "lemon juice", "olive oil", "sea salt"],
        ),
        "Брускетта з томатами": (
            "Tomato Bruschetta",
            "Crispy bread with tomatoes and basil",
            ["ciabatta", "tomatoes", "basil", "garlic", "olive oil", "salt", "balsamic cream"],
        ),
        "Тартар із тунця": (
            "Tuna Tartare",
            "Fresh tuna with capers and onion",
            ["fresh tuna", "red onion", "capers", "avocado", "soy sauce", "lemon", "sesame oil", "cilantro"],
        ),
    },
    "Паста": {
        "Карбонара": (
            "Carbonara",
            "Spaghetti with bacon, egg, and parmesan",
            ["spaghetti", "pancetta bacon", "egg yolks", "parmesan", "garlic", "black pepper", "salt"],
        ),
        "Равіолі з рикоттою": (
            "Ravioli with Ricotta",
            "Homemade ravioli with ricotta and spinach",
            ["flour", "eggs", "ricotta", "spinach", "parmesan", "nutmeg", "butter", "sage"],
        ),
        "Лазанья болоньєзе": (
            "Lasagna Bolognese",
            "Classic lasagna with meat sauce",
            ["lasagna sheets", "ground beef", "tomatoes", "onion", "carrots", "celery", "bechamel sauce", "parmesan", "red wine"],  # noqa: E501
        ),
    },
    "Піца": {
        "Маргарита": (
            "Margherita",
            "Tomato sauce, mozzarella, basil",
            ["pizza dough", "tomato sauce", "mozzarella", "fresh basil", "olive oil", "salt"],
        ),
        "Салямі": (
            "Salami",
            "Pizza with salami, mozzarella, and tomato sauce",
            ["pizza dough", "tomato sauce", "mozzarella", "salami", "oregano", "olive oil"],
        ),
        "Чотири сири": (
            "Four Cheese",
            "Mozzarella, parmesan, gorgonzola, feta",
            ["pizza dough", "mozzarella", "parmesan", "gorgonzola", "feta", "cream", "oregano"],
        ),
        "Прошутто е рукола": (
            "Prosciutto e Rucola",
            "Prosciutto ham, arugula, parmesan",
            ["pizza dough", "tomato sauce", "mozzarella", "prosciutto", "arugula", "parmesan", "balsamic cream"],
        ),
    },
    "Риба та морепродукти": {
        "Лосось з лимонним соусом": (
            "Salmon with Lemon Sauce",
            "Salmon fillet with creamy lemon sauce",
            ["salmon fillet", "heavy cream", "lemon", "capers", "butter", "white wine", "dill", "salt"],
        ),
        "Креветки на грилі": (
            "Grilled Shrimp",
            "Tiger shrimp with garlic butter",
            ["tiger shrimp", "garlic", "butter", "lemon", "parsley", "chili", "olive oil"],
        ),
        "Мідії у білому вині": (
            "Mussels in White Wine",
            "Mussels with garlic and white wine",
            ["mussels", "dry white wine", "garlic", "shallot", "cream", "parsley", "butter", "baguette"],
        ),
    },
    "Вино": {
        "Шардоне біле сухе": (
            "Chardonnay White Dry",
            "France, 0.75L",
            ["Chardonnay grapes", "France", "0.75 L", "13% alc."],
        ),
        "Каберне совіньйон червоне сухе": (
            "Cabernet Sauvignon Red Dry",
            "Chile, 0.75L",
            ["Cabernet Sauvignon grapes", "Chile", "0.75 L", "14% alc."],
        ),
        "Піно Гріджіо": (
            "Pinot Grigio",
            "Italy, 0.75L",
            ["Pinot Grigio grapes", "Italy", "0.75 L", "12.5% alc."],
        ),
    },
    "Коктейлі": {
        "Мохіто": (
            "Mojito",
            "Rum, lime, mint, soda",
            ["white rum", "lime", "fresh mint", "sugar syrup", "soda water", "ice"],
        ),
        "Лонг Айленд": (
            "Long Island",
            "Vodka, gin, rum, tequila, cola",
            ["vodka", "gin", "white rum", "tequila", "triple sec", "lemon juice", "cola", "ice"],
        ),
        "Піна Колада": (
            "Pina Colada",
            "Rum, coconut milk, pineapple juice",
            ["white rum", "coconut milk", "pineapple juice", "ice", "pineapple for garnish"],
        ),
    },
    "Літні салати": {
        "Салат з полуницею": (
            "Strawberry Salad",
            "Salad mix, strawberries, balsamic",
            ["salad mix", "strawberries", "balsamic cream", "pine nuts", "olive oil"],
        ),
        "Грецький з авокадо": (
            "Greek with Avocado",
            "Classic Greek salad with avocado",
            ["cucumber", "tomatoes", "avocado", "feta", "olives", "red onion", "olive oil", "oregano"],
        ),
    },
    "Страви з гриля": {
        "Шашлик зі свинини": (
            "Pork Shashlik",
            "Pork marinated with herbs",
            ["pork neck", "onion", "vinegar", "paprika", "coriander", "black pepper", "salt"],
        ),
        "Бараніна на грилі": (
            "Grilled Lamb",
            "Juicy lamb with rosemary",
            ["lamb", "rosemary", "garlic", "olive oil", "lemon", "thyme", "sea salt"],
        ),
    },
}

MENU_CATEGORY_MAP: dict[str, list[str]] = {
    "Обіднє меню": ["Салати", "Супи", "Гарячі страви", "Гарніри", "Напої", "Десерти"],
    "Вечірнє меню": ["Холодні закуски", "Паста", "Піца", "Риба та морепродукти", "Вино", "Коктейлі"],
    "Сезонне меню": ["Літні салати", "Страви з гриля"],
}


def seed_en_translations(apps: Any, schema_editor: Any) -> None:
    Restaurant = apps.get_model("restaurants", "Restaurant")
    Menu = apps.get_model("menu", "Menu")
    MenuCategory = apps.get_model("menu", "MenuCategory")
    MenuItem = apps.get_model("menu", "MenuItem")
    MenuTranslation = apps.get_model("menu", "MenuTranslation")
    MenuCategoryTranslation = apps.get_model("menu", "MenuCategoryTranslation")
    MenuItemTranslation = apps.get_model("menu", "MenuItemTranslation")

    for restaurant in Restaurant.objects.all():
        for menu_ua, menu_en in MENU_TRANSLATIONS.items():
            try:
                menu = Menu.objects.get(restaurant=restaurant, name=menu_ua)
            except Menu.DoesNotExist:
                continue

            MenuTranslation.objects.update_or_create(
                menu=menu,
                language_code="en",
                defaults={"name": menu_en},
            )

            category_names = MENU_CATEGORY_MAP.get(menu_ua, [])
            for cat_ua in category_names:
                cat_en = CATEGORY_TRANSLATIONS.get(cat_ua, cat_ua)
                try:
                    category = MenuCategory.objects.get(menu=menu, name=cat_ua)
                except MenuCategory.DoesNotExist:
                    continue

                MenuCategoryTranslation.objects.update_or_create(
                    category=category,
                    language_code="en",
                    defaults={"name": cat_en},
                )

                items = CATEGORY_ITEMS.get(cat_ua, {})
                for item_ua, (name_en, desc_en, ingredients_en) in items.items():
                    try:
                        item = MenuItem.objects.get(menu=menu, name=item_ua)
                    except MenuItem.DoesNotExist:
                        continue

                    MenuItemTranslation.objects.update_or_create(
                        menu_item=item,
                        language_code="en",
                        defaults={
                            "name": name_en,
                            "description": desc_en,
                            "ingredients": ingredients_en,
                        },
                    )


def reverse_migration(apps: Any, schema_editor: Any) -> None:
    MenuTranslation = apps.get_model("menu", "MenuTranslation")
    MenuCategoryTranslation = apps.get_model("menu", "MenuCategoryTranslation")
    MenuItemTranslation = apps.get_model("menu", "MenuItemTranslation")
    MenuTranslation.objects.filter(language_code="en").delete()
    MenuCategoryTranslation.objects.filter(language_code="en").delete()
    MenuItemTranslation.objects.filter(language_code="en").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0014_migrate_existing_menu_data_to_translations"),
    ]

    operations = [
        migrations.RunPython(seed_en_translations, reverse_migration),
    ]
