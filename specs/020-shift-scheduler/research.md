# Research: Staff Shift Scheduler

## Decisions

### Decision 1: Restaurant Scoping via JWT (not query params)
- **Decision**: Staff shift views use `RestaurantScopedViewSetMixin` with `get_restaurant_id_from_auth()` to derive restaurant ID from the JWT token.
- **Rationale**: Staff/admin users always authenticate with a restaurant-scoped JWT. Query-param scoping (`?restaurant=<uuid>`) is reserved for public/anonymous views (menu browsing, reservations). The mixin auto-filters querysets and exposes `get_restaurant_id()` via the existing auth helper.
- **Alternatives considered**: `PublicRestaurantQueryMixin` — rejected because staff views should not rely on query params for scoping.

### Decision 2: Same-Day Shifts Only
- **Decision**: Shifts are same-day only (start and end on same calendar date).
- **Rationale**: Spec assumption defers overnight shifts. DB stores `TimeField` for both start and end; no date-crossing logic.
- **Alternatives considered**: DateTimeField spans — would require overnight detection logic; deferred.

### Decision 3: No Overlap Enforcement at DB Level
- **Decision**: Overlapping shifts for the same employee on the same date are not enforced by DB constraints or service-layer validation (FR-013 is SHOULD).
- **Rationale**: Spec marks overlap detection as "SHOULD" and "potential double-booking" as an edge case. Initial implementation is permissive.
- **Alternatives considered**: `CheckConstraint` with `start_time < end_time` for adjacent ranges — complex, non-trivial to express; deferred.

### Decision 4: Atomic Copy with Conflict Rejection
- **Decision**: `copy_shifts` uses `get_or_create` per shift. If a shift already exists for the same employee on a target date, the whole operation raises `IntegrityError` → 409 Conflict.
- **Rationale**: Spec says "entire copy fails" on conflict. Simpler to implement and reason about than partial success.
- **Alternatives considered**: Partial success with skip — adds complexity for ambiguous UX; deferred.

### Decision 5: Month Summary Computed at Query Time
- **Decision**: `get_month_summary` iterates all matching shifts and computes `duration_hours` in Python.
- **Rationale**: Follows constitution pattern (Average Prep Time is query-time derived). No stored aggregates needed at this scale.
- **Alternatives considered**: DB aggregation with `F` expressions — viable but adds complexity; not needed for expected 500-shift/month volume.
