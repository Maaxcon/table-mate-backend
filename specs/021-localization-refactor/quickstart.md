# Quickstart: Localization Validation Guide

## Prerequisites

- Running Django dev server (`python manage.py runserver`)
- Seeded restaurant and menu data (`python manage.py seed_restaurants && python manage.py seed_menu`)

## Setup

1. Run migrations:
   ```bash
   python manage.py migrate
   ```

2. Run data migration (populate translation tables from existing fields):
   ```bash
   python manage.py migrate_translations
   ```

3. Configure restaurant languages:
   ```bash
   python manage.py shell -c "
   from apps.restaurants.models import RestaurantSettings
   s = RestaurantSettings.objects.first()
   s.supported_languages = ['uk', 'en']
   s.locale = 'uk'
   s.save()
   "
   ```

## Validation Scenarios

### 1. Admin Creates Translation

```bash
# Get a menu item ID
ITEM_ID=$(python -c "
import django; django.setup()
from apps.menu.models import MenuItem
print(MenuItem.objects.first().id)
")

# Create English translation
curl -X POST "http://localhost:8000/api/v1/admin/menu-items/$ITEM_ID/translations/" \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"language_code": "en", "name": "Borscht", "description": "Traditional Ukrainian borscht", "ingredients": ["beetroot", "cabbage", "potato"]}'
```

**Expected**: 201 Created. Translation stored in `MenuItemTranslation` table.

### 2. Customer Sees Localized Menu

```bash
# Request menu in English
curl "http://localhost:8000/api/v1/menus/" \
  -H "Accept-Language: en"
```

**Expected**: Menu items show English names and descriptions. Response includes `_lang: "en"`.

### 3. Customer Falls Back to Default Locale

```bash
# Request menu in German (unsupported)
curl "http://localhost:8000/api/v1/menus/" \
  -H "Accept-Language: de"
```

**Expected**: Content in Ukrainian (restaurant's `locale`). Response includes `_lang: "uk"`, `_is_fallback: true`.

### 4. Staff Always Sees Restaurant Locale

```bash
curl "http://localhost:8000/api/v1/staff/menus/" \
  -H "Authorization: Bearer <staff_token>" \
  -H "Accept-Language: en"
```

**Expected**: Content in Ukrainian (restaurant's `locale`). `Accept-Language` is ignored.

### 5. Partial Translation Fallback

Given a menu item with English name but no English description:

```bash
curl "http://localhost:8000/api/v1/menus/" -H "Accept-Language: en"
```

**Expected**: `name` in English, `description` in Ukrainian. Each field falls back independently.

## Verify Database

```bash
python manage.py shell -c "
from apps.menu.models import MenuItemTranslation
print(MenuItemTranslation.objects.count(), 'translations created')
for t in MenuItemTranslation.objects.all()[:5]:
    print(f'  [{t.language_code}] {t.name}')
"
```
