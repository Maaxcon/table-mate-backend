# Research: Scalable Multi-Language Localization Architecture

## 1. Translation Table Design & Fallback Strategy

**Decision**: One translation table per model with a unique constraint on `(parent_fk, language_code)`. Fallback at the query level using `Coalesce` + subquery per field or a single joined prefetch.

**Rationale**:
- Django ORM's `select_related`/`prefetch_related` can eagerly load the correct-language row in one query
- A service-layer `get_localized_content(entity, lang)` function returns a dict with fallback applied per field
- For list endpoints: prefetch all translations for the requested language in one query, then merge in Python

**Alternatives considered**:
- Single giant translation table with generic FK (polymorphic) — complex constraint enforcement, harder to index
- JSONField per model — simpler schema but no FK integrity, harder to query for specific languages

## 2. Migration Strategy for Existing Data

**Decision**: Data migration that copies existing `Menu.name`, `MenuCategory.name`, `MenuItem.name/description/ingredients` into the corresponding translation table row with the restaurant's current `locale` as the language code. Source fields remain as-is (they become "default locale content" semantically).

**Rationale**:
- Zero data loss — existing fields are never dropped
- After migration, the system reads from translation tables; source fields serve as fallback source of truth
- Rollback is trivial (revert reads to source fields)

## 3. Accept-Language Header Parsing

**Decision**: Use Python stdlib `locale` module's `locale.getdefaultlocale()` as last resort, but primary parsing via Django's `django.utils.translation.parse_accept_lang_header` or a lightweight `accept-language` library for weighted priority matching against the restaurant's `supported_languages`.

**Rationale**:
- DRF has no built-in middleware for this; a custom middleware or view-mixin is standard practice
- The middleware sets `request.active_language` which selectors and serializers consume
- Staff requests skip language resolution and use the restaurant's locale directly

## 4. Allergen Localization

**Decision**: Replace hardcoded Ukrainian strings in `seed_menu.py` `_ALLERGEN_RULES` with a language-agnostic key system. Define a mapping `{allergen_key: {locale: label}}` in a data structure or DB table. The seed data uses default locale labels; translations can be added per restaurant.

**Rationale**:
- Decouples allergen labels from code
- Fits the translation table pattern (AllergenLabel model or config dict)
- Low migration cost — only the seed command changes

## 5. Language Middleware Design

**Decision**: Create a `LanguageMiddleware` in `translations/middleware.py` that:
- Skips language resolution for authenticated staff roles (waiter, cook) — always use restaurant locale
- For unauthenticated or customer requests: parse `Accept-Language`, match against restaurant's `supported_languages`, select best match or fallback
- Sets `request.active_language` and `request.active_language_is_fallback` flags
- Serializers check these flags to annotate responses with `_lang` and `_is_fallback` fields

**Rationale**:
- Centralized language resolution vs. per-view logic
- Allows serializers to remain declarative
- Staff bypass ensures POS consistency
