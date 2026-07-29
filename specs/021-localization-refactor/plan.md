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
