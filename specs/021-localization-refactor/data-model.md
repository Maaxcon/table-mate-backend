# Data Model: Scalable Multi-Language Localization

## Translation Tables

### MenuTranslation

| Field | Type | Constraints |
|-------|------|-------------|
| id | BigAutoField | PK |
| menu | ForeignKey(Menu) | NOT NULL, CASCADE on delete |
| language_code | CharField(10) | NOT NULL |
| name | CharField(255) | NOT NULL |
| created_at | DateTimeField | auto_now_add |
| updated_at | DateTimeField | auto_now |

**Unique constraint**: `(menu, language_code)`

### MenuCategoryTranslation

| Field | Type | Constraints |
|-------|------|-------------|
| id | BigAutoField | PK |
| category | ForeignKey(MenuCategory) | NOT NULL, CASCADE on delete |
| language_code | CharField(10) | NOT NULL |
| name | CharField(255) | NOT NULL |
| created_at | DateTimeField | auto_now_add |
| updated_at | DateTimeField | auto_now |

**Unique constraint**: `(category, language_code)`

### MenuItemTranslation

| Field | Type | Constraints |
|-------|------|-------------|
| id | BigAutoField | PK |
| menu_item | ForeignKey(MenuItem) | NOT NULL, CASCADE on delete |
| language_code | CharField(10) | NOT NULL |
| name | CharField(255) | NOT NULL |
| description | TextField | nullable |
| ingredients | JSONField | default list, nullable |
| created_at | DateTimeField | auto_now_add |
| updated_at | DateTimeField | auto_now |

**Unique constraint**: `(menu_item, language_code)`

## Extensions to Existing Models

### RestaurantSettings

| New Field | Type | Default | Constraints |
|-----------|------|---------|-------------|
| supported_languages | JSONField | `["en"]` | List of language codes |

**Note**: `locale` field continues to serve as the default/operating language.

## Language Code Format

- ISO 639-1 two-letter codes: `en`, `uk`, `de`, `fr`, `pl`
- Always stored lowercase
- Validation against a supported-language list per restaurant

## Indexing Strategy

- Translation tables: composite index on `(parent_fk, language_code)` via the unique constraint
- Each translation table also indexes `language_code` alone for language-scoped queries
