# Implementation Plan: Scalable Multi-Language Localization Architecture

**Branch**: `037-localization-refactor` | **Date**: 2026-07-28 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/021-localization-refactor/spec.md`

## Summary

Refactor from a single-locale `RestaurantSettings.locale` field to a scalable architecture where menu display content (Menu.name, MenuCategory.name, MenuItem.name/description/ingredients) is stored in separate per-model translation tables with language-code keys. The restaurant's locale determines staff content; customer endpoints respect `Accept-Language` header with graceful fallback to the default locale.

## Technical Context

**Language/Version**: Python 3.12, Django 5+
**Primary Dependencies**: DRF, PostgreSQL, Redis, Channels
**Storage**: PostgreSQL — separate translation tables per model (MenuTranslation, MenuCategoryTranslation, MenuItemTranslation)
**Testing**: pytest, factory_boy, DRF's API test client
**Target Platform**: Linux server (Django ASGI via Daphne)
**Project Type**: Web service (Django REST backend)
**Performance Goals**: Translated content queries must add <5ms overhead vs. current single-language reads
**Constraints**: Zero-downtime migration for existing production data; backward-compatible API responses
**Scale/Scope**: 10+ languages per restaurant; ~50-200 menu items per restaurant

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Rule | Status | Evidence in Plan |
|------|------|--------|------------------|
| C1 | Right role, right moment, zero ambiguity is preserved | PASS | Localization is purely a content display concern — no real-time state affected. Language selection is backend-authoritative. |
| C2 | Canonical shared entity contracts are preserved | PASS | Menu, MenuCategory, MenuItem gain translatable fields but retain current fields as default-locale content. RestaurantSettings adds `supported_languages`. Existing API shapes preserved. |
| C3 | Role access matrix is backend-enforced and structurally reflected | PASS | Admin gets translation CRUD. Waiter/cook read only in restaurant locale. Backend enforces at the service layer. |
| C4 | Live state uses WebSocket-only typed/versioned events | N/A | No new live events introduced. |
| C5 | Delivery guarantee: at-least-once + reconnect replay | N/A | No new event streams. |
| C6 | Payment confirmation is webhook-only with signature validation | N/A | Payment flows unchanged. |
| C7 | Void flow is atomic with explicit rollback | N/A | Void flows unchanged. |
| C8 | Session lifecycle is explicit (human close, immutable snapshot) | N/A | Session lifecycle unchanged. |
| C9 | Kitchen queue ordering preserves injection-time priority | N/A | Kitchen queue unchanged. |
| C10 | Auth uses role-scoped tokens with immediate invalidation | N/A | Auth unchanged. |
| C11 | Floor layout updates are immutable/versioned | N/A | Floor plan unchanged. |
| C12 | Financial records externally read-only; AVG PREP query-time | N/A | Financial/metrics unchanged. |
| C13 | Frontend-only constraints (role trees, offline, destructive confirm, floor plan perf) | N/A | Frontend contract limited to API response format changes. |
| C14 | Mandatory backend stack and architecture respected | PASS | Uses Django/DRF, Skinny Views / Fat Services / Selectors pattern, model-layer translation tables with service-layer localization resolution. |

## Project Structure

### Documentation (this feature)

```text
specs/021-localization-refactor/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Created by /speckit-tasks
```

### Source Code (repository root)

```text
apps/
├── menu/
│   ├── models/
│   │   ├── __init__.py
│   │   ├── menu.py
│   │   ├── category.py
│   │   ├── item.py
│   │   ├── like.py
│   │   └── translations.py       # MenuTranslation, MenuCategoryTranslation, MenuItemTranslation
│   ├── services/
│   │   ├── __init__.py
│   │   ├── localization.py       # resolve_language(), get_localized_content()
│   │   └── translation_admin.py  # CRUD for translations
│   ├── selectors/
│   │   └── menu_selectors.py     # Existing selectors updated with localization
│   ├── serializers.py            # Existing serializers updated with localized fields
│   └── views.py                  # Existing views updated with language resolution
├── restaurants/
│   └── models.py                 # RestaurantSettings: add supported_languages
└── translations/
    ├── __init__.py
    ├── middleware.py              # Language resolution middleware
    └── language.py               # Language utilities, constants, fallback logic

tests/
├── test_menu_translations.py     # Translation CRUD tests
├── test_localization_middleware.py
└── test_localized_menu_api.py    # Language-aware menu read tests
```

**Structure Decision**: Extended existing Django app structure. `translations/` app for shared localization infra; new `translations.py` model file in menu app; service-layer localization logic in `services/localization.py` for reusability.

## Complexity Tracking

No constitution violations — feature is fully additive and backward-compatible. No entry needed.

---

# Phase 2: Allergen & Ingredient Vocabulary Alignment

**Scope**: FR-014..FR-024, US-5..US-8. Align `Allergen` and `Ingredient` with the default-locale-on-model localization pattern: restaurant-scoped allergen vocabulary, `name` (default locale) on the entity, translations for non-default languages only, free-text (name-based) dish-form entry with get-or-create semantics, orphan pruning on removal/deletion, and name-based reads throughout.

## Technical Decisions

- **Default-locale-on-model**: `get_localized_content` (`services/localization.py`) already falls back to `getattr(entity, field)`; `Allergen`/`Ingredient` must gain a `name` field so that fallback resolves. Translation records hold only non-default languages. Default-locale translation create/update is rejected.
- **Staff operate in default locale**: `LanguageMiddleware` (`apps/translations/middleware.py`) resolves staff requests to `RestaurantSettings.locale`, so free-text dish-form names are always default-locale content and are written to `entity.name`.
- **Name-based matching**: get-or-create matches `entity.name` case-insensitively within the restaurant; on miss, create `name=typed` only (no `key` slug), no translation row is written. Uniqueness is enforced with a `(restaurant, name)` composite constraint.
- **Restaurant scoping**: `Allergen` moves from `BaseModel` to `RestaurantScopedModel`; uniqueness is composite `(restaurant, name)`. `Ingredient` already restaurant-scoped. The legacy `key` field is dropped from both models (T065).
- **Pruning**: generic `prune_orphans(entity_model, through_model, removed_ids)` in services; wired into `AdminMenuItemSerializer.update()` (inside `transaction.atomic`) and `AdminMenuItemViewSet.perform_destroy`. Deletion allowed only when zero `MenuItemAllergen`/`MenuItemIngredient` references remain.
- **Name-based reads**: admin read returns localized names (translation → `entity.name`); `_localized_m2m_names` fallback changes from hardcoded `"uk"`/key to `entity.name`. Public vocab endpoints become restaurant-scoped `[{public_id, name}]`.
- **Seeding**: via data migrations only (existing seed scripts are stale/unused). Migration seeds the standard 14 allergens per restaurant, backfills `name` from the locale-matching translation, removes default-locale translation rows, remaps junction rows per restaurant, and deletes global rows.
- **Frontend**: dish form uses a shared free-text field for both allergens and ingredients (type + Add + chips); no dropdown/`useAllergens`/`fetchAllergens`/`allergenOptions` in the dish flow; `AdminAllergen`/`AdminIngredient` types gain `name`; Translations tab shows `name` as the non-editable primary-language value.
- **Frontend i18n single source of truth**: UI strings live only in `../table-mate-frontend/public/locales/{lng}/translation.json`, loaded at runtime by i18next-http-backend (`/locales/{{lng}}/translation.json`). The bundled `resources` import and `src/i18n/locales/` were removed (T084) so no translations ship in the JS bundle and no second copy can drift. Adding a language requires only dropping a `public/locales/<lng>/translation.json` file (no config change — `supportedLngs` already lists all 23 codes); editing a string means editing `public/locales/{en,uk}/translation.json` only.

## Proposed Work Breakdown

### Backend
1. Models: `Allergen` → `RestaurantScopedModel` + `name`; `Ingredient` + `name`; composite `(restaurant, name)` unique for both; drop the legacy `key` field (`apps/menu/models/__init__.py`, migration `0026`).
2. Migrations (nullable-backfill, 3 steps + key drop): schema (add `name`, nullable `restaurant` FK, drop global `key` unique, add constraint) → data (seed per-restaurant allergens, backfill `name`, drop default-locale translation rows, remap junction rows, delete global rows) → schema (NOT NULL) → drop `key`, enforce `(restaurant, name)`.
3. Serializers (`apps/menu/serializers.py`): `_set_allergens`/`_set_ingredients` get-or-create by name; admin `allergens`/`ingredients` reads via localized-name `SerializerMethodField`; `AdminAllergenSerializer`/`AdminIngredientSerializer` gain `name` + restaurant-scoped uniqueness; reject default-locale translation create/update in `services/__init__.py`.
4. Views (`apps/menu/views.py`): `AdminAllergenViewSet` → `RestaurantScopedViewSetMixin`; public `AllergenListView`/`IngredientListView` → `?restaurant=` + `[{public_id, name}]`; fix `has_translations_for_locale` allergen scope (`services/localization.py:74`).
5. Pruning: `prune_orphans()` in `services/__init__.py`; wire into serializer `update()` (atomic) and `perform_destroy`.
6. Tests (`tests/`): pruning (last-ref-removed → deleted, still-used → kept, cross-restaurant isolation), get-or-create by name (reuse/new-row + translation), name-based admin read, viewset scoping, public endpoint shape, data-migration backfill, default-locale translation rejection.
7. Schema/types: update `schema.yaml`; regenerate FE types.

### Frontend
8. Shared free-text dish-form field for allergens and ingredients (mirror `IngredientsField`); `DishModal` reads/writes names; add `strings.menu.allergens.add`.
9. Remove `useAllergens`, `fetchAllergens`, `allergenOptions.ts` from the dish flow.
10. Add `name` to `AdminAllergen`/`AdminIngredient` types; Translations tab shows `name` as primary language.

## Verification
- Backend: `ruff`, `bandit`, `pytest`.
- Frontend: `npx tsc -b` (pre-existing unrelated errors), `eslint`, `prettier`.
- Rebuild the frontend Docker container after dependency/file changes.

## Known Follow-ups (explicitly deferred)
- Guest `MenuItemModal.ALLERGEN_MAP` hardcoded icon/color map — custom allergens render plain badges.

