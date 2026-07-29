ALLERGEN_KEYS: list[str] = [
    "gluten",
    "milk",
    "eggs",
    "fish",
    "crustaceans",
    "tree_nuts",
    "peanuts",
    "soy",
    "sesame",
    "sulphites",
    "celery",
    "mustard",
    "lupin",
    "molluscs",
]

ALLERGEN_LABELS: dict[str, dict[str, str]] = {
    "gluten": {"en": "Gluten", "uk": "Глютен"},
    "milk": {"en": "Milk", "uk": "Молоко"},
    "eggs": {"en": "Eggs", "uk": "Яйця"},
    "fish": {"en": "Fish", "uk": "Риба"},
    "crustaceans": {"en": "Crustaceans", "uk": "Ракоподібні"},
    "tree_nuts": {"en": "Tree Nuts", "uk": "Горіхи"},
    "peanuts": {"en": "Peanuts", "uk": "Арахіс"},
    "soy": {"en": "Soy", "uk": "Соя"},
    "sesame": {"en": "Sesame", "uk": "Кунжут"},
    "sulphites": {"en": "Sulphites", "uk": "Сульфіти"},
    "celery": {"en": "Celery", "uk": "Селера"},
    "mustard": {"en": "Mustard", "uk": "Гірчиця"},
    "lupin": {"en": "Lupin", "uk": "Люпин"},
    "molluscs": {"en": "Molluscs", "uk": "Молюски"},
}

ALLERGENS = [ALLERGEN_LABELS[key]["en"] for key in ALLERGEN_KEYS]


def get_allergen_labels(language_code: str) -> list[str]:
    """Return allergen labels in the given language, falling back to English."""
    labels = []
    for key in ALLERGEN_KEYS:
        lang_labels = ALLERGEN_LABELS.get(key, {})
        labels.append(lang_labels.get(language_code, lang_labels.get("en", key)))
    return labels
