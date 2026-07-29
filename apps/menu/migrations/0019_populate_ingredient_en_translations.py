from typing import Any

from django.db import migrations, transaction

# Maps Ukrainian ingredient names (from uk IngredientTranslation) to English names.
# Compiled from the same ingredient data used in the seed menu translations.
INGREDIENT_ENGLISH: dict[str, str] = {
    "куряче філе": "Chicken Fillet",
    "салат ромен": "Romaine Lettuce",
    "пармезан": "Parmesan",
    "крутони": "Croutons",
    "соус цезар": "Caesar Dressing",
    "лимонний сік": "Lemon Juice",
    "огірок": "Cucumber",
    "помідори": "Tomatoes",
    "болгарський перець": "Bell Pepper",
    "червона цибуля": "Red Onion",
    "фета": "Feta",
    "оливки": "Olives",
    "оливкова олія": "Olive Oil",
    "орегано": "Oregano",
    "лосось філе": "Salmon Fillet",
    "філе лосося": "Salmon Fillet",
    "картопля": "Potatoes",
    "шпинат": "Spinach",
    "гірчиця": "Mustard",
    "сіль": "Salt",
    "перець": "Pepper",
    "буряк": "Beetroot",
    "капуста": "Cabbage",
    "морква": "Carrots",
    "цибуля": "Onion",
    "томатна паста": "Tomato Paste",
    "яловичина": "Beef",
    "сметана": "Sour Cream",
    "пампушки": "Pampushky",
    "часник": "Garlic",
    "печериці": "Mushrooms",
    "вершки": "Heavy Cream",
    "масло": "Butter",
    "курячий бульйон": "Chicken Broth",
    "мускатний горіх": "Nutmeg",
    "ковбаса копчена": "Smoked Sausage",
    "шинка": "Ham",
    "огірки мариновані": "Pickled Cucumbers",
    "каперси": "Capers",
    "лимон": "Lemon",
    "яйце": "Egg",
    "яйця": "Eggs",
    "панірувальні сухарі": "Breadcrumbs",
    "зелень": "Herbs",
    "стейк рібай": "Ribeye Beef",
    "часникове масло": "Garlic Butter",
    "розмарин": "Rosemary",
    "чебрець": "Thyme",
    "морська сіль": "Sea Salt",
    "чорний перець": "Black Pepper",
    "овочі гриль": "Grilled Vegetables",
    "паприка": "Paprika",
    "свинина": "Pork",
    "борошно": "Flour",
    "молоко": "Milk",
    "олія соняшникова": "Sunflower Oil",
    "соус на вибір": "Choice of Sauce",
    "кабачки": "Zucchini",
    "баклажани": "Eggplant",
    "прованські трави": "Provencal Herbs",
    "рис пропарений": "Steamed Rice",
    "кукурудза": "Corn",
    "горошок": "Peas",
    "сухофрукти": "Dried Fruits",
    "груша": "Pear",
    "яблуко": "Apple",
    "чорнослив": "Prunes",
    "вода": "Water",
    "цукор": "Sugar",
    "смородина чорна": "Blackcurrant",
    "вишня": "Cherry",
    "малина": "Raspberry",
    "чай чорний": "Black Tea",
    "кава арабіка": "Arabica Coffee",
    "маскарпоне": "Mascarpone",
    "печиво савоярді": "Ladyfingers",
    "еспресо": "Espresso",
    "амаретто": "Amaretto",
    "какао": "Cocoa",
    "вершки 33%": "Cream",
    "стабілізатор": "Stabilizer",
    "топінг на вибір": "Choice of Topping",
    "вершковий сир": "Cream Cheese",
    "ваніль": "Vanilla",
    "пісочне печиво": "Shortbread Cookies",
    "яловича вирізка": "Beef Tenderloin",
    "рукола": "Arugula",
    "чіабатта": "Ciabatta",
    "базилік": "Basil",
    "бальзамічний крем": "Balsamic Cream",
    "тунець свіжий": "Fresh Tuna",
    "авокадо": "Avocado",
    "соєвий соус": "Soy Sauce",
    "кунжутна олія": "Sesame Oil",
    "кінза": "Cilantro",
    "спагеті": "Spaghetti",
    "бекон панчетта": "Pancetta Bacon",
    "жовтки": "Egg Yolks",
    "рікотта": "Ricotta",
    "шавлія": "Sage",
    "листи лазаньї": "Lasagna Sheets",
    "яловичий фарш": "Ground Beef",
    "селера": "Celery",
    "соус бешамель": "Bechamel Sauce",
    "червоне вино": "Red Wine",
    "тісто для піци": "Pizza Dough",
    "томатний соус": "Tomato Sauce",
    "моцарела": "Mozzarella",
    "салямі": "Salami",
    "горгонзола": "Gorgonzola",
    "прошуто": "Prosciutto",
    "біле вино": "White Wine",
    "кріп": "Dill",
    "креветки тигрові": "Tiger Shrimp",
    "петрушка": "Parsley",
    "чилі": "Chili",
    "мідії": "Mussels",
    "вино біле сухе": "Dry White Wine",
    "шалот": "Shallot",
    "багет": "Baguette",
    "виноград шардоне": "Chardonnay Grapes",
    "франція": "France",
    "виноград каберне": "Cabernet Sauvignon Grapes",
    "чилі": "Chile",
    "виноград піно гріджіо": "Pinot Grigio Grapes",
    "італія": "Italy",
    "ром білий": "White Rum",
    "лайм": "Lime",
    "м'ята свіжа": "Fresh Mint",
    "цукровий сироп": "Sugar Syrup",
    "содова вода": "Soda Water",
    "лід": "Ice",
    "горілка": "Vodka",
    "джин": "Gin",
    "текіла": "Tequila",
    "тріпл сек": "Triple Sec",
    "кола": "Cola",
    "кокосове молоко": "Coconut Milk",
    "ананасовий сік": "Pineapple Juice",
    "ананас для прикраси": "Pineapple for Garnish",
    "салатна суміш": "Salad Mix",
    "полуниця": "Strawberries",
    "кедрові горіхи": "Pine Nuts",
    "свиняча шия": "Pork Neck",
    "оцет": "Vinegar",
    "коріандр": "Coriander",
    "баранина": "Lamb",
    "овочі": "Vegetables",
    "помідори чері": "Cherry Tomatoes",
    "соус песто": "Pesto Sauce",
    "соус ранч": "Ranch Sauce",
    "кетчуп": "Ketchup",
    "майонез": "Mayonnaise",
    "гірчиця зерниста": "Whole Grain Mustard",
    "мед": "Honey",
    "імбир": "Ginger",
    "куркума": "Turmeric",
    "лавровий лист": "Bay Leaf",
    "перець духмяний": "Allspice",
    "гвоздика": "Clove",
    "кориця": "Cinnamon",
    "ванільний цукор": "Vanilla Sugar",
    "розпушувач": "Baking Powder",
    "сода": "Baking Soda",
    "дріжджі": "Yeast",
    "сир твердий": "Hard Cheese",
    "сир моцарела": "Mozzarella",
    "сир пармезан": "Parmesan",
    "сир фета": "Feta",
    "сир горгонзола": "Gorgonzola",
    "сир рікотта": "Ricotta",
    "сир маскарпоне": "Mascarpone",
    "сир вершковий": "Cream Cheese",
    "шинка прошуто": "Prosciutto",
    "бекон": "Bacon",
    "ковбаса": "Sausage",
    "курка": "Chicken",
    "свинина": "Pork",
    "телятина": "Veal",
    "риба": "Fish",
    "лосось": "Salmon",
    "тунець": "Tuna",
    "тріска": "Cod",
    "креветки": "Shrimp",
    "мідії": "Mussels",
    "кальмари": "Squid",
    "мікс салатів": "Salad Mix",
    "салат айсберг": "Iceberg Lettuce",
    "салат фрізе": "Frisee",
    "цибуля зелена": "Green Onion",
    "цибуля фіолетова": "Purple Onion",
    "цибуля ріпчаста": "Yellow Onion",
    "яблучний оцет": "Apple Cider Vinegar",
    "бальзамічний оцет": "Balsamic Vinegar",
    "рисовий оцет": "Rice Vinegar",
    "олія рослинна": "Vegetable Oil",
    "олія вершкове": "Butter",
    "соус териякі": "Teriyaki Sauce",
    "соус барбекю": "BBQ Sauce",
    "соус тартар": "Tartar Sauce",
    "соус сирний": "Cheese Sauce",
    "сметана": "Sour Cream",
    "йогурт": "Yogurt",
    "соус кисло-солодкий": "Sweet and Sour Sauce",
    "арахіс": "Peanuts",
    "мигдаль": "Almonds",
    "волоські горіхи": "Walnuts",
    "фісташки": "Pistachios",
    "родзинки": "Raisins",
    "журавлина": "Cranberries",
    "чорниця": "Blueberries",
    "ожина": "Blackberries",
    "банан": "Banana",
    "апельсин": "Orange",
    "грейпфрут": "Grapefruit",
    "манго": "Mango",
    "ананас": "Pineapple",
    "ківі": "Kiwi",
    "персик": "Peach",
    "абрикос": "Apricot",
    "виноград": "Grapes",
    "кавун": "Watermelon",
    "диня": "Melon",
    "м'ята": "Mint",
    "меліса": "Lemon Balm",
    "естрагон": "Tarragon",
    "кмин": "Cumin",
    "каррі": "Curry",
    "хмелі-сунелі": "Khmeli-Suneli",
    "аджика": "Adjika",
    "лаваш": "Lavash",
    "тортилья": "Tortilla",
    "кукурудзяні чіпси": "Corn Chips",
    "соус гуакамоле": "Guacamole",
    "соус сальса": "Salsa",
    "слівки": "Cream",
    "масло вершкове": "Butter",
    "яйце куряче": "Egg",
    "спеції": "Spices",
    "приправи": "Seasoning",
    "томат": "Tomato",
    "перець болгарський": "Bell Pepper",
    "огірок свіжий": "Cucumber",
    "м'ясний фарш": "Ground Meat",
    "куряче філе": "Chicken Fillet",
    "філе куряче": "Chicken Fillet",
}


def _derive_english_name_obj(ingredient: Any, uk_name: str) -> str:
    if uk_name in INGREDIENT_ENGLISH:
        return INGREDIENT_ENGLISH[uk_name]
    if uk_name.lower() in INGREDIENT_ENGLISH:
        return INGREDIENT_ENGLISH[uk_name.lower()]
    key = ingredient.key
    if key and all(c.isascii() and (c.isalpha() or c in "-' ") for c in key):
        return key.replace("-", " ").replace("_", " ").strip().title()
    return uk_name


def populate_ingredient_en_translations(apps: Any, schema_editor: Any) -> None:
    Ingredient = apps.get_model("menu", "Ingredient")
    IngredientTranslation = apps.get_model("menu", "IngredientTranslation")

    batch: list[IngredientTranslation] = []
    batch_size = 200

    for ingredient in Ingredient.objects.iterator(chunk_size=batch_size):
        if IngredientTranslation.objects.filter(
            ingredient=ingredient, language_code="en",
        ).exists():
            continue

        uk_name = (
            IngredientTranslation.objects
            .filter(ingredient=ingredient, language_code="uk")
            .values_list("name", flat=True)
            .first()
        ) or ingredient.key

        en_name = _derive_english_name_obj(ingredient, uk_name)

        batch.append(
            IngredientTranslation(
                ingredient=ingredient,
                language_code="en",
                name=en_name,
            )
        )

        if len(batch) >= batch_size:
            with transaction.atomic():
                IngredientTranslation.objects.bulk_create(
                    batch, ignore_conflicts=True,
                )
            batch.clear()

    if batch:
        with transaction.atomic():
            IngredientTranslation.objects.bulk_create(
                batch, ignore_conflicts=True,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0018_migrate_to_m2m_fields"),
    ]

    operations = [
        migrations.RunPython(
            populate_ingredient_en_translations,
            migrations.RunPython.noop,
        ),
    ]
