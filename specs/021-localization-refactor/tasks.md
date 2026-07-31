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
- Frontend at `../table-mate-frontend/` (sibling repo)

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

## Phase 7: User Story 8 — Default-Locale Name Stored on the Entity (Priority: P1) ⚠️ BLOCKS US-5..US-7

**Goal**: `Allergen` and `Ingredient` store their default-locale display `name` directly on the entity (the pattern used by Menu/MenuCategory/MenuItem), and translation records hold only non-default languages. This phase also carries the model + data-migration foundation that US-5, US-6, and US-7 depend on (per plan.md Phase 2).

**Independent Test**: Create an allergen/ingredient in a restaurant with locale "uk" via the admin API — the Ukrainian name lands in `entity.name`; an English translation is stored in the translation table; a create/update translation request for `language_code == locale` is rejected with 400.

### Implementation for User Story 8

- [X] T038 [US8] Update `Allergen` and `Ingredient` models in `apps/menu/models/__init__.py`:
  - Add `name = models.CharField(max_length=255)` to both
  - Move `Allergen` from `BaseModel` to `RestaurantScopedModel` (`restaurant` FK, `on_delete=PROTECT`), drop the global `unique=True` on `key`, add composite `UniqueConstraint(fields=["restaurant", "key"], name="allergen_restaurant_key_unique")` (mirrors `ingredient_restaurant_key_unique`)
  - Update `__str__` to return `self.name or self.key`
- [X] T039 [US8] Generate the base schema migration `apps/menu/migrations/0023_allergen_ingredient_vocab_alignment.py` via `makemigrations menu` (nullable additions only):
  - `Allergen.name` nullable, `Ingredient.name` nullable, `Allergen.restaurant` nullable FK — so the data step below can run without losing rows (3-step nullable-backfill pattern)
- [X] T040 [US8] Add the `RunPython` data step + final NOT NULL `AlterField`s to `apps/menu/migrations/0023_allergen_ingredient_vocab_alignment.py`:
  - Seed the standard 14 allergens per restaurant from `apps/menu/allergens.py` (`ALLERGEN_KEYS`/`ALLERGEN_LABELS`) using each restaurant's `RestaurantSettings.locale` label as `name`
  - Backfill `Allergen.restaurant_id` by remapping `MenuItemAllergen` rows to per-restaurant allergen copies (via `MenuItem.restaurant_id`), then delete the now-unreferenced global allergen rows
  - Backfill `Allergen.name`/`Ingredient.name` from the locale-matching translation row (fallback: any available translation, then key)
  - Delete `AllergenTranslation`/`IngredientTranslation` rows whose `language_code` equals the entity's restaurant `locale` (default-locale content now lives on the entity)
  - Finish with `AlterField` on `name` and `Allergen.restaurant` → `null=False`
- [X] T041 [P] [US8] Add `name` (read/write) to `AdminAllergenSerializer` and `AdminIngredientSerializer` in `apps/menu/serializers.py`; add restaurant-scoped uniqueness validation for `name` (case-insensitive, excluding self), mirroring the existing `validate_key` pattern (`apps/menu/serializers.py:448`)
- [X] T042 [P] [US8] Reject default-locale translations for Allergen and Ingredient: in `apps/menu/services/__init__.py` gate `create_allergen_translation`/`update_allergen_translation`/`create_ingredient_translation`/`update_ingredient_translation` and the view actions in `apps/menu/views.py` (raise `ValidationError` when `language_code == get_restaurant_locale(...)`, mirroring `AdminMenuItemViewSet.create_translation` at `apps/menu/views.py:461`)
- [X] T043 [P] [US8] Add `name: string` to `AdminAllergen` and `AdminIngredient` in `../table-mate-frontend/src/features/admin/types.ts`
- [X] T044 [US8] Update the Translations tab in `../table-mate-frontend/src/features/admin/pages/TranslationsSection/TranslationsSection.tsx` so allergen/ingredient rows show `entity.name` as the non-editable primary-language value (update `getEntityName` to prefer `name` over `key`)

**Checkpoint**: Allergens/ingredients carry a default-locale `name` on the entity; default-locale translation writes are rejected; both models are restaurant-scoped and backfilled by migration.

---

## Phase 8: User Story 7 — Each Restaurant Has Its Own Allergen Vocabulary (Priority: P2)

**Goal**: Allergen vocabulary is scoped per restaurant (matching ingredients), with admin and public endpoints returning only the requesting restaurant's entries.

**Independent Test**: Create the same allergen name "Gluten" in two restaurants — the entries are independent; admin list for restaurant A returns only A's entries; the public allergen endpoint is restricted to `?restaurant=`.

### Implementation for User Story 7

- [X] T045 [US7] Scope `AdminAllergenViewSet` in `apps/menu/views.py:520` to the admin's restaurant: add `RestaurantScopedViewSetMixin` + `restaurant_lookup = "restaurant_id"`, keep `IsAdmin`, move the `translations` prefetch into `safely_get_queryset`, and set `restaurant_id=require_restaurant_id_from_auth(...)` in `perform_create` (mirror `AdminIngredientViewSet` at `apps/menu/views.py:577`)
- [X] T046 [US7] Scope `AdminAllergenViewSet` translation actions in `apps/menu/views.py:528-573` and `apps/menu/services/__init__.py` (`create_allergen_translation`/`update_allergen_translation`/`get_allergen_translations`) to the admin's restaurant (filter by `allergen__restaurant_id`) so a token can only touch its own restaurant's allergens
- [X] T047 [US7] Update `AllergenListView` in `apps/menu/views.py:766` to be restaurant-scoped like `IngredientListView` (`apps/menu/views.py:797`): require `?restaurant=` (resolve `Restaurant.public_id` → id, 404 on missing), filter `Allergen.objects.filter(restaurant_id=...)`, return `[{"key": ..., "name": ...}]` localized (translation → `entity.name`); update the `extend_schema` responses + `OpenApiParameter`
- [X] T048 [P] [US7] Fix `has_translations_for_locale` allergen scope in `apps/menu/services/localization.py:74` to filter `AllergenTranslation.objects.filter(allergen__restaurant_id=restaurant_id, language_code=language_code)` (currently unscoped)

**Checkpoint**: Allergen CRUD and both public vocab endpoints are restaurant-scoped and return `{key, name}`.

---

## Phase 9: User Story 5 — Admin Adds Allergens and Ingredients to a Dish by Typing Names (Priority: P1)

**Goal**: Dish create/edit accepts free-text allergen and ingredient display names; the backend get-or-creates the vocabulary entry (case-insensitive within the restaurant) and returns display names on read.

**Independent Test**: POST/PATCH a dish with a new typed allergen name and a new typed ingredient name via the admin API — both vocabulary entries are created for the restaurant; re-typing the same name (with different case/whitespace) reuses the same entry; GET returns display names.

### Implementation for User Story 5

- [X] T049 [US5] In `AdminMenuItemSerializer` (`apps/menu/serializers.py:267`), replace `ingredients`/`allergens` `M2MThroughKeysField` read with name-based reads: add `SerializerMethodField`s returning localized names (translation → `entity.name`); keep write as a `ListField` of name strings
- [X] T050 [US5] Rewrite `_set_allergens`/`_set_ingredients` in `apps/menu/serializers.py:349-368` to get-or-create by name: match `name__iexact` + trimmed within `restaurant_id`; on miss create `name=typed, key=slugify(name)` with slug-collision disambiguation (append `-2`, `-3`, …); write no translation row (staff requests resolve to the restaurant locale, so the typed name is default-locale content)
- [X] T051 [US5] Update public `MenuItemSerializer._localized_m2m_names` in `apps/menu/serializers.py:97-106` to fall back to `entity.name` (then `entity.key`) instead of the hardcoded `"uk"` fallback; delete `M2MThroughKeysField` class if left unused (`apps/menu/serializers.py:250`)
- [X] T052 [US5] Replace the `AllergensField` dropdown (`../table-mate-frontend/src/features/admin/components/DishModal/AllergensField.tsx`) with the free-text type + Add + chips pattern from `IngredientsField.tsx` (extract a shared component in `DishModal/` if desired); add `add` to `strings.menu.allergens` in `../table-mate-frontend/src/features/admin/strings.ts` and add the `admin.menu.allergens.add` key to `src/i18n/locales/{en,uk}/translation.json`, syncing the same keys into `public/locales/{en,uk}/translation.json`
- [X] T053 [P] [US5] Remove the allergen options fetch from the dish flow: drop `options`/`useAllergens` usage in `DishModal.tsx`, remove `useAllergens` from `../table-mate-frontend/src/features/admin/hooks/useAllergens.ts` (and `constants/allergenOptions.ts` if nothing else imports them), and remove `fetchAllergens` from `../table-mate-frontend/src/features/admin/api/menu.ts:196`

**Checkpoint**: Admin dish form and API are free-text for allergens/ingredients; new names create entries, known names reuse them; reads return display names.

---

## Phase 10: User Story 6 — Admin Removes an Allergen or Ingredient; Unused Entries Are Pruned (Priority: P1)

**Goal**: When the last dish reference to an allergen/ingredient is removed (or the dish is deleted), the backend deletes the now-unreferenced vocabulary entry automatically.

**Independent Test**: Remove the only dish reference to an allergen via the admin API — the entry is deleted; remove one of two references — the entry is kept; deleting a dish prunes entries referenced only by it.

### Implementation for User Story 6

- [X] T054 [US6] Add `prune_orphans(entity_model, through_model, removed_ids)` to `apps/menu/services/__init__.py`: delete vocabulary entries (scoped by restaurant) whose `through_model` reference count dropped to zero after the caller removed the dish's references; return the number deleted
- [X] T055 [P] [US6] Wire pruning into `AdminMenuItemSerializer.update()` in `apps/menu/serializers.py:335-347`: capture the removed allergen/ingredient ids before wiping, wrap the wipe/recreate + prune in `transaction.atomic()` (per plan.md — all-or-nothing)
- [X] T056 [P] [US6] Wire pruning into dish deletion in `apps/menu/views.py`: in `AdminMenuItemViewSet.perform_destroy` capture through ids before `instance.delete()` then call `prune_orphans` inside `transaction.atomic()`; also prune in the `delete` action of `bulk_update_items` (`apps/menu/services/__init__.py:54-58`)

**Checkpoint**: Orphaned vocabulary entries are pruned on reference removal and dish deletion, while entries still referenced (including across restaurants) are preserved.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T029 [P] Update seed menu command `apps/menu/management/commands/seed_menu.py`:
  - Refactor `_ALLERGEN_RULES` to use language-agnostic keys instead of hardcoded Ukrainian labels
  - Create allergen label mapping `ALLERGEN_LABELS = {key: {locale: label}}`
  - Populate default locale labels during seeding
- [X] T030 [P] Add `AllergenLabel` model or config in `apps/menu/allergens.py` for locale-aware allergen display
- [X] T031 [P] Update existing menu admin to include translation tables in admin UI (`apps/menu/admin.py`)
- [X] T057 [P] Write tests for US-7/US-8 in `tests/test_allergen_ingredient_scoping.py`:
  - Name stored on the entity (default-locale content), translation stored separately
  - Default-locale translation create/update rejected (FR-022)
  - Per-restaurant allergen independence + admin list scoping (US-7)
  - Data-migration backfill correctness (names, junction remap, default-locale translation rows dropped, global rows deleted)
- [X] T058 [P] Write tests for US-5 in `tests/test_menu_item_vocab_names.py`:
  - get-or-create by name: new row creation, case/whitespace-insensitive reuse (US-5 AS4), no duplication
  - Name-based admin read round-trip (create with names → GET returns names)
  - Public `MenuItemSerializer` allergen/ingredient localized-name fallback to `entity.name`
- [X] T059 [P] Write tests for US-6 in `tests/test_vocab_pruning.py`:
  - Last reference removed → entry deleted; still referenced by another dish → kept (US-6 AS1/AS2/AS3)
  - Dish deletion prunes unreferenced entries; entries still referenced elsewhere preserved (US-6 AS4)
  - Cross-restaurant isolation (US-7 AS3): pruning one restaurant's entry never touches another's
- [X] T060 [P] Write tests for public endpoints in `tests/test_vocab_public_endpoints.py`:
  - `AllergenListView` requires `?restaurant=`, is scoped, returns `[{key, name}]` localized (FR-024)
  - `IngredientListView` unchanged shape `[{key, name}]` after fallback change
- [X] T061 [P] Update `schema.yaml` in the repo root (run `drf-spectacular` schema export) and regenerate the frontend OpenAPI types (`../table-mate-frontend/schema.yaml` → `src/types/api/types.gen.ts`) so `AdminAllergen`/`AdminIngredient` include `name` and the dish serializer documents name-based `allergens`/`ingredients` (canonical shared-entity contract compatibility per constitution §II)
- [ ] T062 [P] Extend `specs/021-localization-refactor/quickstart.md` with allergen/ingredient validation scenarios (free-text create/reuse, pruning, per-restaurant scoping) and run the end-to-end validation against a seeded dev DB
- [X] T063 [P] Run backend quality gates on changed files: `ruff check .`, `bandit`, `pytest` (all `tests/`)
- [X] T064 [P] Run frontend quality gates in `../table-mate-frontend`: `npx tsc -b` (pre-existing unrelated errors only), `eslint`, `prettier`; rebuild the frontend Docker container (`table-mate-backend_frontend_1`)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - US1 and US4 can proceed in parallel (translation CRUD vs. language config)
  - US2 depends on US1 (localized reads need translations to exist)
  - US3 depends on US2 (staff localization shares the same content resolution logic)
- **User Story 8 (Phase 7)**: Depends on Foundational — **BLOCKS US-5, US-6, US-7** (model changes + migration are the shared foundation)
- **User Story 7 (Phase 8)**: Depends on US-8 (model + migration done)
- **User Story 5 (Phase 9)**: Depends on US-8 (`name` field + migration) — can proceed in parallel with US-7
- **User Story 6 (Phase 10)**: Depends on US-8 and US-5 (pruning operates on name-based get-or-create flows) — can proceed in parallel with US-7
- **Polish (Phase 11)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 8 (P1)**: Foundation — no dependency on other new stories; all of US-5..US-7 consume its model/migration output
- **User Story 7 (P2)**: Depends on US-8; independent of US-5/US-6
- **User Story 5 (P1)**: Depends on US-8; independent of US-7
- **User Story 6 (P1)**: Depends on US-8 and US-5; independent of US-7

### Within Each User Story

- Tests (if included) MUST be written and FAIL before implementation
- Models before services
- Services before endpoints
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- T038 (models) must precede T039/T040 (migration) and T041-T044
- T041/T042 (serializers + services) can run in parallel after T040
- T043/T044 (frontend types + Translations tab) can run in parallel with the backend tasks
- T045/T046/T047 share `apps/menu/views.py` — run sequentially; T048 (localization.py) runs in parallel
- T049/T050/T051 share `apps/menu/serializers.py` — run sequentially
- T052/T053 are separate frontend files — can run in parallel
- T054 (service) before T055/T056 (both consume `prune_orphans`); T055 and T056 touch different files
- All test tasks T057-T060 can run in parallel (separate test files)
- T061-T064 can run in parallel at the end

---

## Parallel Example: User Story 8

```bash
# Backend model/migration (sequential chain):
Task: "T038 Update Allergen/Ingredient models in apps/menu/models/__init__.py"
Task: "T039 Generate schema migration apps/menu/migrations/0023_allergen_ingredient_vocab_alignment.py"
Task: "T040 Add RunPython data step + NOT NULL finalize to the 0023 migration"

# Then launch serializer/service + frontend in parallel:
Task: "T041 Add name to AdminAllergenSerializer/AdminIngredientSerializer in apps/menu/serializers.py"
Task: "T042 Reject default-locale allergen/ingredient translations in apps/menu/services/__init__.py"
Task: "T043 Add name to AdminAllergen/AdminIngredient in ../table-mate-frontend/src/features/admin/types.ts"
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
5. Add US8 (name-on-entity + migration) → foundation for vocabulary alignment
6. Add US7 (per-restaurant allergen scoping) → vocabulary isolation
7. Add US5 (free-text entry) → dish form saves new vocabulary
8. Add US6 (pruning) → no orphan accumulation
9. Polish (tests, schema/types, quickstart)

### Parallel Team Strategy

With multiple developers:

1. Team completes Phase 1 + 2 together
2. Once Foundational is done:
   - Developer A: US1 (translation CRUD) + US4 (language config)
   - Developer B: US2 (localized reads, depends on US1)
   - Developer C: US3 (staff localization, depends on US2)
3. After US8 (model/migration) lands:
   - Developer A: US7 (allergen scoping)
   - Developer B: US5 (free-text entry, backend + frontend)
   - Developer C: US6 (pruning)
4. Polish tasks distributed after all stories merge

---

## Notes

- No live state, WebSocket events, or real-time delivery involved — localization is a REST-layer concern
- No payment, void, session, or financial data affected
- C14 (backend stack) requires Django/DRF patterns — all tasks follow Skinny Views / Fat Services / Selectors
- Each user story is independently testable via API calls with different auth tokens and Accept-Language headers
- All existing menu data is preserved via the T009 data migration — rollback by reverting reads to source fields
- US-5..US-8 carry canonical shared-entity contract changes (Allergen/Ingredient gain `name`, become restaurant-scoped) — schema.yaml + FE type regeneration is T061
- Default-locale content lives on the entity (`name`); translation tables hold only non-default languages; default-locale translation writes are rejected (FR-022)
- Vocabulary is provisioned through data migrations only; legacy seed scripts (`apps/menu/management/commands/seed_menu.py`) are stale and unused
- Guest `MenuItemModal.ALLERGEN_MAP` hardcoded icon/color map is explicitly deferred (see plan.md Known Follow-ups)
