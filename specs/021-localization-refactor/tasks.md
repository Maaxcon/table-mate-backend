---

description: "Task list for Scalable Multi-Language Localization Architecture"
---

# Tasks: Scalable Multi-Language Localization Architecture

**Input**: Design documents from `specs/021-localization-refactor/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- Django project root at repository root
- Apps under `apps/`
- Tests under `tests/`
- Paths shown below assume the existing Django project structure

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure for translations

- [X] T001 Create `apps/translations/` app directory with `__init__.py`, `apps.py`, `middleware.py`, `language.py`
- [X] T002 Register `apps.translations` in `INSTALLED_APPS` in `core/settings/base.py`
- [X] T003 [P] Create translation model files: `apps/menu/models/__init__.py` (package init)
- [X] T004 [P] Create `apps/menu/models/translations.py` with `MenuTranslation`, `MenuCategoryTranslation`, `MenuItemTranslation` models per data-model.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Localization Infrastructure

- [X] T005 [P] Implement language resolution utilities in `apps/translations/language.py`:
  - `parse_accept_language_header()` — parse weighted `Accept-Language` header
  - `select_best_match(preferred, supported)` — match against restaurant's supported_languages
  - `LANGUAGE_CODE_REGEX` constant for ISO 639-1 validation
- [X] T006 [P] Implement `LanguageMiddleware` in `apps/translations/middleware.py`:
  - Skip resolution for authenticated staff roles (waiter, cook, admin) — always use restaurant locale
  - For unauthenticated or customer requests: parse Accept-Language, match against restaurant's supported_languages, select best match or fallback
  - Set `request.active_language` and `request.active_language_is_fallback` flags
- [X] T007 Add `supported_languages` JSONField to `RestaurantSettings` model in `apps/restaurants/models.py` (default `["en"]`)
- [X] T008 Add validation on `RestaurantSettings.locale` to ensure it is a member of `supported_languages`

### Data Migration

- [X] T009 Create data migration `apps/menu/migrations/XXXX_migrate_existing_menu_data_to_translations.py`:
  - For each Menu, MenuCategory, MenuItem: create a translation row with the restaurant's current `locale` as the language_code, copying `name` (and `description`/`ingredients` for MenuItem) from the source fields
  - Handle restaurants where `locale` is not yet set — default to "en"

### Checkpoint: Foundation ready — user story implementation can now begin in parallel

---

## Phase 3: User Story 1 — Restaurant Admin Sets Up Menu Translations (Priority: P1) 🎯 MVP

**Goal**: Admin users can create, read, update, and delete translations for Menu names, MenuCategory names, and MenuItem names/descriptions/ingredients via REST API.

**Independent Test**: POST a translation for a menu item in English, then GET all translations for that item — verify the English translation is stored and retrievable alongside the default locale content.

### Implementation for User Story 1

- [X] T010 [P] [US1] Create `apps/menu/serializers.py` — add `MenuTranslationSerializer`, `MenuCategoryTranslationSerializer`, `MenuItemTranslationSerializer` with validation for language_code format and content fields
- [X] T011 [P] [US1] Implement translation CRUD service in `apps/menu/services/translation_admin.py`:
  - `create_menu_translation(menu_id, language_code, name)`
  - `update_menu_translation(menu_id, language_code, data)`
  - `delete_menu_translation(menu_id, language_code)`
  - Same pattern for MenuCategory and MenuItem
  - Enforce unique constraint `(parent, language_code)`
- [X] T012 [P] [US1] Add admin translation endpoints in `apps/menu/views.py`:
  - `POST /api/v1/admin/menus/{id}/translations/`
  - `PUT /api/v1/admin/menus/{id}/translations/{lang}/`
  - `DELETE /api/v1/admin/menus/{id}/translations/{lang}/`
  - `GET /api/v1/admin/menus/{id}/translations/`
- [X] T013 [P] [US1] Add admin translation endpoints for MenuCategory in `apps/menu/views.py`:
  - `POST /api/v1/admin/menu-categories/{id}/translations/`
  - `PUT /api/v1/admin/menu-categories/{id}/translations/{lang}/`
  - `DELETE /api/v1/admin/menu-categories/{id}/translations/{lang}/`
- [X] T014 [P] [US1] Add admin translation endpoints for MenuItem in `apps/menu/views.py`:
  - `POST /api/v1/admin/menu-items/{id}/translations/`
  - `PUT /api/v1/admin/menu-items/{id}/translations/{lang}/`
  - `DELETE /api/v1/admin/menu-items/{id}/translations/{lang}/`
  - `GET /api/v1/admin/menu-items/{id}/translations/`
- [X] T015 [US1] Wire up admin translation URL routes in `apps/menu/urls.py`
- [X] T016 [US1] Add admin-only permission checks on all translation CRUD endpoints (IsAdminUser or custom permission per role access matrix)

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently — admin can create/read/update/delete translations via API.

---

## Phase 4: User Story 2 — Customer Browses Menu in Preferred Language (Priority: P1)

**Goal**: Customer-facing menu endpoints return content in the language requested via `Accept-Language` header, with fallback to the restaurant's default locale.

**Independent Test**: Create a menu item with Ukrainian (default) and English translations. Send `Accept-Language: en` in the request — verify the response shows English content. Send `Accept-Language: de` (unsupported) — verify Ukrainian fallback content with `_is_fallback: true`.

### Implementation for User Story 2

- [X] T017 [P] [US2] Implement `get_localized_content()` service in `apps/menu/services/localization.py`:
  - Accept an entity instance and a language_code
  - Query the corresponding Translation table for the given language
  - Return a dict with each field resolved (translated value or fallback to entity source field)
  - Handle partial translations per-field (e.g., name translated, description not — return name from translation, description from source)
- [X] T018 [P] [US2] Implement bulk localization helper in `apps/menu/services/localization.py`:
  - `localize_queryset(queryset, model_class, translation_model_class, language_code)`
  - Prefetch all translations for the given language in one query
  - Merge into model instances as a `_localized` attribute with fallback applied
- [X] T019 [P] [US2] Update customer-facing menu selectors in `apps/menu/selectors/menu_selectors.py`:
  - Modify existing menu list/detail selectors to call `localize_queryset()` using `request.active_language`
  - Ensure staff endpoints bypass localization and use restaurant locale directly
- [X] T020 [P] [US2] Update customer-facing serializers in `apps/menu/serializers.py`:
  - Modify existing `MenuListSerializer`, `MenuDetailSerializer` etc. to emit `_lang` and `_is_fallback` fields from request context
  - Use localized content from `_localized` attribute when available
- [X] T021 [US2] Add `LanguageMiddleware` to `MIDDLEWARE` in `core/settings/base.py`
- [X] T022 [US2] Update existing customer menu view endpoints in `apps/menu/views.py` to ensure `request.active_language` is consumed by selectors

**Checkpoint**: Customer menu endpoints now return localized content based on Accept-Language header with graceful fallback.

---

## Phase 5: User Story 3 — Waiter Verifies Localized Menu Display in POS (Priority: P2)

**Goal**: Staff-facing (waiter, cook) menu endpoints always return content in the restaurant's configured locale, ignoring any user language preference.

**Independent Test**: Send a staff-authenticated request to the staff menu endpoint with `Accept-Language: en` while the restaurant's locale is "uk" — verify the response content is in Ukrainian.

### Implementation for User Story 3

- [X] T023 [P] [US3] Update staff-serving menu selectors in `apps/menu/selectors/menu_selectors.py`:
  - Create or modify `staff_menu_list()` and `staff_menu_detail()` to explicitly use `restaurant.locale` instead of `request.active_language`
- [X] T024 [P] [US3] Update staff-serving serializers in `apps/menu/serializers.py`:
  - Create `StaffMenuSerializer` variants that omit `_is_fallback` (staff always gets the restaurant locale, never a fallback)
  - Include `_lang` field set to the restaurant's locale
- [X] T025 [US3] Verify `LanguageMiddleware` in `apps/translations/middleware.py` correctly skips language resolution for staff roles (waiter, cook, admin)

**Checkpoint**: Staff menu endpoints consistently return content in the restaurant's operating language regardless of request headers.

---

## Phase 6: User Story 4 — Admin Manages Languages per Restaurant (Priority: P2)

**Goal**: Restaurant admins can configure supported languages and set the default language for their restaurant.

**Independent Test**: PATCH the restaurant settings to set `supported_languages: ["uk", "en", "de"]` and `locale: "en"`. Then GET the settings — verify the update is reflected. Attempt to set `locale: "fr"` where fr is not in supported_languages — verify rejection.

### Implementation for User Story 4

- [X] T026 [P] [US4] Add `supported_languages` to `RestaurantSettingsSerializer` in `apps/restaurants/serializers.py` with validation:
  - All language codes must match ISO 639-1 format (lowercase, 2 letters)
  - `locale` must be a member of `supported_languages`
  - At least one language must be configured
- [X] T027 [P] [US4] Update `RestaurantSettings` update service in `apps/restaurants/services.py` to handle `supported_languages` field
- [X] T028 [US4] Verify language configuration validation in `apps/restaurants/models.py`:
  - Add model-level validation to ensure `locale` is always in `supported_languages`
  - Reject save with `ValidationError` if violated

**Checkpoint**: Admins can configure which languages their restaurant supports and change the default language.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T029 [P] Update seed menu command `apps/menu/management/commands/seed_menu.py`:
  - Refactor `_ALLERGEN_RULES` to use language-agnostic keys instead of hardcoded Ukrainian labels
  - Create allergen label mapping `ALLERGEN_LABELS = {key: {locale: label}}`
  - Populate default locale labels during seeding
- [X] T030 [P] Add `AllergenLabel` model or config in `apps/menu/allergens.py` for locale-aware allergen display
- [X] T031 [P] Update existing menu admin to include translation tables in admin UI (`apps/menu/admin.py`)
- [ ] T032 [P] Write tests for translation CRUD in `tests/test_menu_translations.py`:
  - Test create, update, delete for each translation model
  - Test unique constraint enforcement
  - Test validation (invalid language codes, empty names)
- [ ] T033 [P] Write tests for localization middleware in `tests/test_localization_middleware.py`:
  - Test Accept-Language parsing and best-match selection
  - Test staff bypass (staff role ignores Accept-Language)
  - Test fallback to restaurant locale when no match
- [ ] T034 [P] Write tests for localized menu API in `tests/test_localized_menu_api.py`:
  - Test customer menu list returns content in requested language
  - Test partial translation fallback per-field
  - Test `_lang` and `_is_fallback` response fields
- [ ] T035 [P] Write tests for language configuration in `tests/test_restaurant_settings.py`:
  - Test supported_languages validation
  - Test locale must be in supported_languages
- [ ] T036 Run quickstart.md validation scenarios end-to-end and fix any issues
- [ ] T037 Run lint (`ruff check .`) and type checks (`mypy .`) on all changed files

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - US1 and US4 can proceed in parallel (translation CRUD vs. language config)
  - US2 depends on US1 (localized reads need translations to exist)
  - US3 depends on US2 (staff localization shares the same content resolution logic)
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2 — No dependencies on other stories
- **User Story 4 (P2)**: Can start after Phase 2 — independent from US1
- **User Story 2 (P1)**: Depends on US1 (needs translation data to localize)
- **User Story 3 (P2)**: Depends on US2 (shares localization service layer)

### Within Each User Story

- Models before services
- Services before endpoints
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- T005, T006, T007, T008 (Phase 2 foundational) can run in parallel
- T010-T014 (US1 models/serializers/services) can run in parallel
- T017-T020 (US2 localization service/serializers) can run in parallel
- US1 and US4 can be developed in parallel
- All Phase 7 polish tasks (T029-T035) can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch all models/serializers for US1 together:
Task: "Create MenuTranslationSerializer in apps/menu/serializers.py"
Task: "Implement translation CRUD service in apps/menu/services/translation_admin.py"
Task: "Add admin translation endpoints in apps/menu/views.py"
Task: "Wire up admin translation URL routes in apps/menu/urls.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 + 4)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1 (translation CRUD)
4. Complete Phase 6: User Story 4 (language config)
5. **STOP and VALIDATE**: Admin can configure languages + create translations
6. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 (translation CRUD) + US4 (language config) → MVP: admin can manage translations in multiple languages
3. Add US2 (customer localized reads) → Customers see menu in their language
4. Add US3 (staff localized display) → Staff POS consistent
5. Polish (allergen localization, tests, seed data update)

### Parallel Team Strategy

With multiple developers:

1. Team completes Phase 1 + 2 together
2. Once Foundational is done:
   - Developer A: US1 (translation CRUD) + US4 (language config)
   - Developer B: US2 (localized reads, depends on US1)
   - Developer C: US3 (staff localization, depends on US2)
3. Polish tasks distributed after all stories merge

---

## Notes

- No live state, WebSocket events, or real-time delivery involved — localization is a REST-layer concern
- No payment, void, session, or financial data affected
- C14 (backend stack) requires Django/DRF patterns — all tasks follow Skinny Views / Fat Services / Selectors
- Each user story is independently testable via API calls with different auth tokens and Accept-Language headers
- All existing menu data is preserved via the T009 data migration — rollback by reverting reads to source fields
