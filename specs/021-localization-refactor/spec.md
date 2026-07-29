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

### Edge Cases

- What happens when a translation field is partially filled (some fields translated, others not)? Fallback to default locale content per field.
- How does the system handle language codes that do not match any supported locale? Reject with a clear error message on configuration, silently fallback on read.
- How are existing untranslated menu items handled after the migration? Existing data is treated as the default locale content; no data loss.
- What happens during bulk menu import or seed operations? The import creates content in the restaurant's default locale only; translations can be added later.

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

### Non-Functional Requirements

- **NFR-001**: Adding translations MUST NOT require downtime or schema migrations for existing production data
- **NFR-002**: Read queries for localized content MUST NOT add significant latency compared to current single-language queries
- **NFR-003**: The translation architecture MUST support at least 10 languages per restaurant without performance degradation
- **NFR-004**: Admin translation management MUST be accessible via the existing API patterns (not require a separate translation management UI in v1)

### Canonical Contract Impact

- **Impacted Entities**: Menu, MenuCategory, MenuItem, RestaurantSettings, MenuItemLike (allergens display)
- **Contract Delta**:
  - `RestaurantSettings`: Add `supported_languages` (list of language codes), extend `locale` semantics as default language
  - `Menu.name`: Becomes translatable (stored content is default locale)
  - `MenuCategory.name`: Becomes translatable
  - `MenuItem.name`, `MenuItem.description`, `MenuItem.ingredients`: Become translatable
  - Allergen labels: Become locale-aware for display purposes
- **Backend Source of Truth Rule**: Backend selects and returns the correct language content; client never selects translation variant

### Role Access Matrix

- **Cook**: View menu items in restaurant's configured locale only; no translation management access
- **Cook Restricted**: Cannot create or modify translations
- **Waiter**: View menu content in restaurant's configured locale only; no translation management access
- **Waiter Restricted**: Cannot create or modify translations
- **Admin**: Full read/write access to all translations for their managed restaurant
- **Admin Restricted**: Cannot set unsupported language codes as default

### Key Entities

- **RestaurantSettings**: Extends to include `supported_languages` configuration; `locale` becomes the default language for fallback and staff-facing operations
- **Menu / MenuCategory / MenuItem**: Core menu entities whose display-oriented text fields (name, description, ingredients) become translatable
- **Allergen System**: Hardcoded Ukrainian labels in seed data need to be locale-aware

## Success Criteria

### Measurable Outcomes

- **SC-001**: An admin can add a complete set of translations for a restaurant's menu (all items in 2+ languages) using the API without any code changes or deployment
- **SC-002**: A customer browsing the menu with a language preference sees all available content in their language, with missing translations gracefully falling back to the default locale
- **SC-003**: Staff POS menu responses always return content in the restaurant's configured locale regardless of the request's language headers
- **SC-004**: All existing menu data from before migration is preserved and treated as the restaurant's default locale content
- **SC-005**: Adding a new supported language to a restaurant does not require any database schema changes or application redeployment

## Assumptions

- The existing `RestaurantSettings.locale` field will be repurposed as the restaurant's default operating language (it currently stores "en" or "uk")
- Translation management in v1 is API-only; a dedicated admin translation UI is out of scope
- The system will use the `Accept-Language` HTTP header as the customer's language preference signal
- Notifications, order data, and operational fields (prices, availability, sort order) are NOT translatable — only display-oriented content fields are in scope
- The existing Django i18n infrastructure (`USE_I18N = True`) will be leveraged for static/source-level translations (labels, messages, validation errors), while translatable model content uses a separate storage mechanism
- Frontend integration (language switcher UI, translation management UI) is out of scope for this backend refactoring
