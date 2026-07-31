# Feature Specification: Scalable Multi-Language Localization Architecture

**Feature Branch**: `021-localization-refactor`
**Created**: 2026-07-28
**Status**: Draft
**Input**: User description: "refactoring the current translation approach into the Scalable Multi-Language Localization Architecture"

## User Scenarios & Testing

### User Story 1 - Restaurant Admin Sets Up Menu Translations (Priority: P1)

A restaurant admin wants to offer their menu in multiple languages so that international customers can browse items in their preferred language.

**Why this priority**: Core value proposition — without stored translations, there is no multi-language support to expose to any user.

**Independent Test**: Can be tested entirely via the admin interface or API by creating a translated version of a menu item and verifying it is stored and retrievable.

**Acceptance Scenarios**:

1. **Given** a restaurant with locale "uk", **When** an admin adds an English translation for a menu item with name "Greek Salad", **Then** the English translation is stored alongside the original Ukrainian name
2. **Given** a menu item with translations in Ukrainian and English, **When** queried without a language preference, **Then** the restaurant's default locale content is returned
3. **Given** a menu category with translations, **When** an admin updates only the translated fields, **Then** the original language content is preserved

---

### User Story 2 - Customer Browses Menu in Preferred Language (Priority: P1)

A customer browsing the menu sees content in their preferred language when available, falling back to the restaurant's default language.

**Why this priority**: This is the end-user-facing value that makes translations useful.

**Independent Test**: Can be tested by sending API requests with different language preferences and verifying the returned content is in the expected language.

**Acceptance Scenarios**:

1. **Given** a menu item has translations in Ukrainian and English, **When** a customer requests the menu list with English language preference, **Then** the item name and description are returned in English
2. **Given** a menu item has only Ukrainian content and no English translation, **When** a customer requests with English language preference, **Then** the Ukrainian content is returned as fallback
3. **Given** a restaurant with locale "uk", **When** a customer requests the menu without specifying a language, **Then** the restaurant's default language (Ukrainian) content is returned

---

### User Story 3 - Waiter Verifies Localized Menu Display in POS (Priority: P2)

A waiter using the POS interface sees menu item names in the restaurant's operating language.

**Why this priority**: Staff workflows should be consistent and unaffected by customer language preferences.

**Independent Test**: Can be tested by verifying that the waiter-facing menu endpoints always return content in the restaurant's configured locale.

**Acceptance Scenarios**:

1. **Given** a restaurant with locale "uk", **When** a waiter fetches the menu via the staff API, **Then** all menu content is returned in Ukrainian
2. **Given** a restaurant with locale "en", **When** a waiter fetches the menu via the staff API, **Then** all menu content is returned in English

---

### User Story 4 - Admin Manages Languages per Restaurant (Priority: P2)

A restaurant admin can configure which languages their restaurant supports and set the default language.

**Why this priority**: Language configuration is a prerequisite for any translation workflow.

**Independent Test**: Can be tested by updating restaurant settings with language configuration and verifying API behavior reflects the change.

**Acceptance Scenarios**:

1. **Given** a restaurant settings page, **When** an admin adds English and German as supported languages, **Then** the system accepts translations in those languages
2. **Given** a restaurant with two supported languages, **When** an admin changes the default language from Ukrainian to English, **Then** new requests without language preference return English content
3. **Given** an unsupported language code, **When** an admin attempts to set it as default, **Then** the system rejects the configuration

---

### User Story 5 - Admin Adds Allergens and Ingredients to a Dish by Typing Names (Priority: P1)

A restaurant admin creates or edits a dish and adds allergens and ingredients by typing their display names directly (free text), instead of selecting from a fixed dropdown. The system creates or reuses the underlying vocabulary entry automatically.

**Why this priority**: This is how dish creation works today for ingredients and how allergens must behave to be consistent; without it the dish form cannot save new vocabulary.

**Independent Test**: Can be tested by creating/editing a dish via the admin API with a new typed allergen and ingredient name and verifying the entry is stored, reused on subsequent saves, and returned by name.

**Acceptance Scenarios**:

1. **Given** a dish creation form, **When** an admin types a new allergen name and a new ingredient name, **Then** the dish saves and both vocabulary entries are created for the restaurant
2. **Given** an allergen already named "Глютен" in the restaurant, **When** an admin types "Глютен" on another dish, **Then** the same entry is reused, not duplicated
3. **Given** a dish being edited, **When** it is reopened, **Then** its allergens and ingredients are shown as their display names, not internal identifiers
4. **Given** an admin types an allergen name, **When** the name differs only in case or whitespace from an existing entry, **Then** the existing entry is reused

---

### User Story 6 - Admin Removes an Allergen or Ingredient; Unused Entries Are Pruned (Priority: P1)

When an allergen or ingredient is removed from a dish, the system checks whether any other dish in the restaurant still references the same entry. If no dish references it, the entry is deleted automatically.

**Why this priority**: Prevents orphaned vocabulary from accumulating while preserving entries still in use.

**Independent Test**: Can be tested by removing an allergen/ingredient from a dish via the admin API and verifying the entry is deleted when unused and preserved when still referenced.

**Acceptance Scenarios**:

1. **Given** an allergen referenced only by dish A, **When** the admin removes it from dish A, **Then** the allergen entry is deleted
2. **Given** an allergen referenced by dishes A and B, **When** the admin removes it from dish A, **Then** the entry is kept because dish B still references it
3. **Given** an ingredient referenced only by dish A, **When** the admin removes it from dish A, **Then** the ingredient entry is deleted
4. **Given** a dish is deleted, **When** the deletion completes, **Then** allergen and ingredient entries referenced only by that dish are also deleted

---

### User Story 7 - Each Restaurant Has Its Own Allergen Vocabulary (Priority: P2)

Allergen vocabulary is scoped per restaurant, matching how ingredients already behave. Each restaurant manages an independent set of allergen entries.

**Why this priority**: Consistency with the ingredient model and isolation between restaurants.

**Independent Test**: Can be tested by creating the same allergen name in two restaurants and verifying the entries are independent and scoped.

**Acceptance Scenarios**:

1. **Given** two restaurants, **When** each creates an allergen named "Gluten", **Then** the two entries are independent and do not conflict
2. **Given** an admin of restaurant A, **When** they list allergens, **Then** only restaurant A's allergen entries are returned
3. **Given** an allergen removed from all of restaurant A's dishes, **When** restaurant B still references its own "Gluten", **Then** only restaurant A's entry is affected

---

### User Story 8 - Default-Locale Name Stored on the Entity (Priority: P1)

The default-locale display name for allergens and ingredients is stored directly on the entity, matching the pattern used by Menu, MenuCategory, and MenuItem. Translation records hold only non-default languages.

**Why this priority**: This is the localization architecture's fallback contract; without it, display resolution cannot fall back to the default locale.

**Independent Test**: Can be tested by creating an allergen/ingredient in a restaurant with locale "uk" and verifying its Ukrainian name is stored on the entity, while an added English translation is stored separately.

**Acceptance Scenarios**:

1. **Given** a restaurant with locale "uk", **When** an allergen is created with name "Глютен", **Then** the name is stored on the allergen entity itself
2. **Given** an allergen with "Глютен" on the entity, **When** an admin adds an English translation "Gluten", **Then** it is stored as a translation record, not on the entity
3. **Given** an allergen with only a Ukrainian name, **When** a customer requests content in English, **Then** the Ukrainian name is returned as fallback
4. **Given** a translation request for the restaurant's default language, **When** an admin attempts to create it, **Then** the system rejects it because that content lives on the entity

---

### Edge Cases

- What happens when a translation field is partially filled (some fields translated, others not)? Fallback to default locale content per field.
- How does the system handle language codes that do not match any supported locale? Reject with a clear error message on configuration, silently fallback on read.
- How are existing untranslated menu items handled after the migration? Existing data is treated as the default locale content; no data loss.
- What happens during bulk menu import or seed operations? The import creates content in the restaurant's default locale only; translations can be added later.
- What happens when a typed allergen/ingredient name differs only in case or whitespace from an existing entry? The existing entry is reused (case-insensitive, trimmed matching).
- What happens when an admin types the same allergen name in a different language than the existing entry? It is treated as a new entry, since matching is scoped to the active language (documented limitation to keep behavior predictable).
- What happens when a vocabulary entry is referenced by dishes in more than one restaurant? Entries are restaurant-scoped, so a dish can only ever reference an entry in its own restaurant; pruning is isolated per restaurant.
- What happens when two typed names resolve to the same internal identifier? The system disambiguates the internal identifier so no entry is lost or overwritten.
- What happens when a dish is deleted while referencing allergens/ingredients? Entries referenced only by that dish are pruned; entries still referenced elsewhere are preserved.
- How does the system avoid creating a translation for the restaurant's default language? Such requests are rejected, since the default-language content is stored on the entity itself.

## Requirements

### Functional Requirements

- **FR-001**: System MUST support storing translatable content for Menu names, MenuCategory names, MenuItem names, descriptions, and ingredients in multiple languages
- **FR-002**: System MUST allow each restaurant to configure a list of supported languages and a default language
- **FR-003**: System MUST return content in the restaurant's default locale when no language preference is specified in the request
- **FR-004**: System MUST fall back to the restaurant's default locale content when a requested translation is not available for a specific field
- **FR-005**: Admin users MUST be able to create, update, and delete translations for any translatable content field via the API
- **FR-006**: Staff-facing endpoints (cook, waiter) MUST always return content in the restaurant's configured locale, ignoring user language preference
- **FR-007**: Customer-facing menu endpoints MUST respect the requested language preference when available
- **FR-008**: The existing `RestaurantSettings.locale` field semantics MUST be preserved: it represents the restaurant's default operating language
- **FR-009**: Allergen label system MUST support localization so allergen names appear in the correct language
- **FR-010**: Translation data MUST be stored such that adding a new language does not require schema changes
- **FR-011**: System MUST provide a migration path for existing untranslated content — existing data becomes the default locale content with no data loss
- **FR-012**: API responses for translatable content MUST include a language indicator so clients know which language was returned
- **FR-013**: System MUST store translations in separate translation tables per model (MenuTranslation, MenuCategoryTranslation, MenuItemTranslation), each with a FK to the parent entity, a language code field, and translated field columns
- **FR-014**: Allergen vocabulary MUST be scoped per restaurant, so each restaurant manages its own set of allergen entries independently of other restaurants
- **FR-015**: Allergen and Ingredient entities MUST store their default-locale display name directly on the entity, and translation records MUST hold only non-default languages
- **FR-016**: Admin dish creation and editing MUST support adding allergens and ingredients by typing display names as free text
- **FR-017**: When a typed allergen or ingredient name matches an existing entry in the restaurant for the active language, the system MUST reuse that entry; otherwise it MUST create a new entry automatically
- **FR-018**: When an allergen or ingredient is removed from a dish and no other dish in the restaurant references it, the system MUST automatically delete that vocabulary entry
- **FR-019**: When a dish is deleted, the system MUST prune allergen and ingredient entries that become unreferenced by any dish
- **FR-020**: Admin dish read responses MUST return allergen and ingredient display names (localized, falling back to the entity's default-locale name), never internal identifiers
- **FR-021**: Customer-facing dish responses MUST show allergen and ingredient names in the active language, falling back to the entity's default-locale name
- **FR-022**: Translation management MUST reject creating or editing a translation for the restaurant's default language
- **FR-023**: The standard allergen vocabulary MUST be provisioned per restaurant through database migrations, not runtime seed scripts
- **FR-024**: Public allergen and ingredient vocabulary endpoints MUST be restaurant-scoped and return both the stable key and the localized display name

### Non-Functional Requirements

- **NFR-001**: Adding translations MUST NOT require downtime or schema migrations for existing production data
- **NFR-002**: Read queries for localized content MUST NOT add significant latency compared to current single-language queries
- **NFR-003**: The translation architecture MUST support at least 10 languages per restaurant without performance degradation
- **NFR-004**: Admin translation management MUST be accessible via the existing API patterns (not require a separate translation management UI in v1)

### Canonical Contract Impact

- **Impacted Entities**: Menu, MenuCategory, MenuItem, RestaurantSettings, MenuItemLike (allergens display), Allergen, Ingredient
- **Contract Delta**:
  - `RestaurantSettings`: Add `supported_languages` (list of language codes), extend `locale` semantics as default language
  - `Menu.name`: Becomes translatable (stored content is default locale)
  - `MenuCategory.name`: Becomes translatable
  - `MenuItem.name`, `MenuItem.description`, `MenuItem.ingredients`: Become translatable
  - Allergen labels: Become locale-aware for display purposes
  - `Allergen`: Becomes restaurant-scoped and gains a default-locale `name` field; translations hold only non-default languages
  - `Ingredient`: Gains a default-locale `name` field; translations hold only non-default languages
  - `MenuItem.allergens` / `MenuItem.ingredients` (admin read/write): Carried as display names instead of internal identifiers
- **Backend Source of Truth Rule**: Backend selects and returns the correct language content; client never selects translation variant

### Role Access Matrix

- **Cook**: View menu items in restaurant's configured locale only; no translation management access
- **Cook Restricted**: Cannot create or modify translations
- **Waiter**: View menu content in restaurant's configured locale only; no translation management access
- **Waiter Restricted**: Cannot create or modify translations
- **Admin**: Full read/write access to all translations for their managed restaurant; full management of their restaurant's allergen and ingredient vocabulary
- **Admin Restricted**: Cannot set unsupported language codes as default; cannot create translations in the restaurant's default language

### Key Entities

- **RestaurantSettings**: Extends to include `supported_languages` configuration; `locale` becomes the default language for fallback and staff-facing operations
- **Menu / MenuCategory / MenuItem**: Core menu entities whose display-oriented text fields (name, description, ingredients) become translatable
- **Allergen System**: Hardcoded Ukrainian labels in seed data need to be locale-aware
- **Allergen**: Restaurant-scoped vocabulary entry with a default-locale `name`, a stable key, and translations for non-default languages; automatically created from typed dish-form names and pruned when unreferenced
- **Ingredient**: Restaurant-scoped vocabulary entry with a default-locale `name`, a stable key, and translations for non-default languages; automatically created from typed dish-form names and pruned when unreferenced

## Success Criteria

### Measurable Outcomes

- **SC-001**: An admin can add a complete set of translations for a restaurant's menu (all items in 2+ languages) using the API without any code changes or deployment
- **SC-002**: A customer browsing the menu with a language preference sees all available content in their language, with missing translations gracefully falling back to the default locale
- **SC-003**: Staff POS menu responses always return content in the restaurant's configured locale regardless of the request's language headers
- **SC-004**: All existing menu data from before migration is preserved and treated as the restaurant's default locale content
- **SC-005**: Adding a new supported language to a restaurant does not require any database schema changes or application redeployment
- **SC-006**: An admin can create or edit a dish typing any allergen and ingredient display name, and the entry is reused or created automatically without a save error
- **SC-007**: Removing the last dish reference to an allergen or ingredient deletes the entry automatically, while entries still referenced by another dish are preserved
- **SC-008**: Two restaurants can each maintain independent allergen vocabularies containing the same names without conflict
- **SC-009**: Allergen and ingredient names shown in dish forms and customer views are localized display names (never internal identifiers), with the default-locale name stored on the entity as the fallback

## Assumptions

- The existing `RestaurantSettings.locale` field will be repurposed as the restaurant's default operating language (it currently stores "en" or "uk")
- Translation management in v1 is API-only; a dedicated admin translation UI is out of scope
- The system will use the `Accept-Language` HTTP header as the customer's language preference signal
- Notifications, order data, and operational fields (prices, availability, sort order) are NOT translatable — only display-oriented content fields are in scope
- The existing Django i18n infrastructure (`USE_I18N = True`) will be leveraged for static/source-level translations (labels, messages, validation errors), while translatable model content uses a separate storage mechanism
- Frontend integration (language switcher UI, translation management UI) is out of scope for this backend refactoring
- Staff-operated admin dish forms always enter allergen/ingredient names in the restaurant's default locale (staff requests resolve to the restaurant's configured locale)
- Name matching for typed allergens/ingredients is scoped to the active language only; the same concept typed in two different languages is treated as two entries (accepted limitation)
- Vocabulary provisioning happens through data migrations; legacy seed scripts are stale and unused
- The guest-facing allergen icon/color map is hardcoded and out of scope for this feature
