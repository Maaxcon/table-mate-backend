# API Contracts: Localization

## Language Resolution

### Staff Endpoints

All staff-authenticated endpoints (waiter, cook, admin roles) bypass `Accept-Language` and return content in the restaurant's `locale` (default language). The response includes:

```json
{
  "_lang": "uk",
  "_is_fallback": false,
  "name": "Борщ український",
  ...
}
```

### Customer Endpoints

Customer-facing menu endpoints resolve language via the `Accept-Language` header:

1. Parse weighted language tags from the header
2. Match against the restaurant's `supported_languages` list
3. Select best match (highest priority supported language)
4. If no match found, fall back to restaurant's `locale`
5. Set `_is_fallback: true` when the returned language differs from the requested best match

**Example request**:
```
GET /api/v1/menus/
Accept-Language: en;q=0.9, de;q=0.5
```

**Response (restaurant supports en and uk)**:
```json
{
  "_lang": "en",
  "_is_fallback": false,
  "items": [
    {
      "name": "Borscht",
      "description": "Traditional Ukrainian borscht with pampushky"
    }
  ]
}
```

## Translation CRUD (Admin Only)

### Create Translation

```
POST /api/v1/admin/menus/{menu_id}/translations/
Content-Type: application/json

{
  "language_code": "en",
  "name": "Lunch Menu"
}
```

### Update Translation

```
PUT /api/v1/admin/menu-items/{item_id}/translations/{lang}/

{
  "name": "Caesar Salad",
  "description": "Classic Caesar with chicken fillet",
  "ingredients": ["chicken fillet", "romaine lettuce", "parmesan"]
}
```

### Delete Translation

```
DELETE /api/v1/admin/menu-categories/{cat_id}/translations/{lang}/
```

### Batch: Get All Translations for Entity

```
GET /api/v1/admin/menus/{menu_id}/translations/
```

Returns all available translations keyed by language_code.

## Language Configuration

```
PATCH /api/v1/admin/restaurants/{rest_id}/settings/

{
  "supported_languages": ["uk", "en", "de"],
  "locale": "uk"
}
```

Validation:
- `locale` must be in `supported_languages`
- Each language code must match ISO 639-1 format
- At least one language must be configured
