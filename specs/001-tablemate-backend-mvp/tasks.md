# Tasks: Tablemate Backend MVP API

**Input**: Design documents from `/specs/001-tablemate-backend-mvp/`  
**Prerequisites**: `spec.md` (plan not yet generated; tasks derived directly from specification)  
**Tests**: Included for API contracts, permissions, and websocket flows  
**Organization**: Tasks grouped by user story with foundational blockers first

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: `US1..US5` mapping to spec user stories

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Align repository shape with backend constitution and target project structure.

- [ ] T001 Create settings package split by adding `core/settings/__init__.py`, `core/settings/base.py`, `core/settings/local.py`, `core/settings/production.py` and move logic from `core/settings.py`.
- [ ] T002 [P] Add environment template updates in `.env.example` for `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_HOSTS`.
- [ ] T003 [P] Update dependency files `requirements/base.txt`, `requirements/dev.txt`, `requirements/prod.txt` with `djangorestframework-simplejwt`, Google token verification dependency, and Redis/Channels runtime deps.
- [ ] T004 Create missing app skeleton `apps/users/` with `apps.py`, `models.py`, `selectors.py`, and init files.
- [ ] T005 [P] Refactor orders package structure to `apps/orders/models/cart_session.py`, `apps/orders/models/cart_item.py`, `apps/orders/api/v1/{views.py,serializers.py,urls.py}` with `__init__.py` files.
- [ ] T006 [P] Add missing architecture files across apps: `services.py` and `selectors.py` in `apps/authentication`, `apps/restaurants`, `apps/editor`, `apps/reservations`, `apps/menu`, `apps/orders`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core platform behavior required before user-story work.

**CRITICAL**: No user-story implementation should start before this phase is complete.

- [ ] T007 Implement `common/mixins.py` with `UUIDMixin` and `TimestampMixin` and migrate models to use them.
- [ ] T008 Implement `common/exceptions.py` with base domain exception + `ReservationConflictError` and standard error payload mapping.
- [ ] T009 Implement role permissions in `common/permissions.py` (`IsRoot`, `IsOwner`, `IsAdmin`, `IsWaiter`, `IsCook`, `IsGuest`) or equivalent role policy classes.
- [ ] T010 Configure DRF + JWT in `core/settings/base.py` with `simplejwt` authentication and default permission policy.
- [ ] T011 Configure Channels + Redis layer in `core/settings/base.py` and websocket entry in `core/asgi.py`.
- [ ] T012 Update root routing in `core/urls.py` and `core/routing.py` for API includes and websocket routes (`ws/cart/:session_id/`, `ws/hall/`).
- [ ] T013 Add backend quality gates to `.github/workflows/main.yml` for lint/security/tests (`flake8`, `bandit`, `safety`, test suite).

**Checkpoint**: Architecture, auth infrastructure, and routing foundation are ready for feature implementation.

---

## Phase 3: User Story 1 - Google OAuth + JWT Auth (Priority: P1)

**Goal**: Complete token exchange and identity endpoints.

**Independent Test**: Auth endpoints work end-to-end with valid and invalid tokens.

### Tests for User Story 1

- [ ] T014 [P] [US1] Add auth API contract tests in `tests/contract/test_auth_api.py` for `/api/auth/google/`, `/api/auth/refresh/`, `/api/auth/me/`, `/api/auth/logout/`.
- [ ] T015 [P] [US1] Add auth integration tests in `tests/integration/test_google_jwt_flow.py` for success/failure paths.

### Implementation for User Story 1

- [ ] T016 [US1] Implement `apps/users/models.py` custom `User` model with UUID PK, unique email, profile fields, and role enum.
- [ ] T017 [US1] Implement `apps/users/selectors.py` with `get_user_by_email()` and helper lookup functions.
- [ ] T018 [US1] Implement `apps/authentication/services.py` Google verification and JWT issuance workflow.
- [ ] T019 [US1] Implement auth serializers and views in `apps/authentication/api/serializers.py` and `apps/authentication/api/views.py`.
- [ ] T020 [US1] Wire auth URLs in `apps/authentication/api/urls.py` and include from `core/urls.py`.
- [ ] T021 [US1] Add/logout token invalidation strategy and error handling in auth service layer.

**Checkpoint**: Auth endpoints return JWTs and identity reliably.

---

## Phase 4: User Story 2 - Reservation with Conflict Guard (Priority: P1)

**Goal**: Safe table availability + reservation creation under concurrency.

**Independent Test**: Parallel reservation attempts create one success + one 409 conflict.

### Tests for User Story 2

- [ ] T022 [P] [US2] Add reservation API contract tests in `tests/contract/test_reservations_api.py` for create/list/status endpoints.
- [ ] T023 [P] [US2] Add concurrency integration test in `tests/integration/test_reservation_conflict.py` for transaction race guard.

### Implementation for User Story 2

- [ ] T024 [US2] Implement `apps/editor/models.py` table fields (position, shape, status, active, capacity) using mixins.
- [ ] T025 [US2] Implement `apps/reservations/models.py` reservation model with guest/table/time interval/status fields.
- [ ] T026 [US2] Implement availability selectors in `apps/editor/selectors.py` and guest reservation selectors in `apps/reservations/selectors.py`.
- [ ] T027 [US2] Implement `check_availability()` and transaction-safe `create_reservation()` in `apps/reservations/services.py`.
- [ ] T028 [US2] Implement reservation serializers/views/urls in `apps/reservations/api/{serializers.py,views.py,urls.py}`.
- [ ] T029 [US2] Implement editor table read/availability/position endpoints in `apps/editor/api/{serializers.py,views.py,urls.py}`.

**Checkpoint**: Reservation and table availability APIs are stable and conflict-safe.

---

## Phase 5: User Story 3 - Public Menu + Protected Access Elsewhere (Priority: P1)

**Goal**: Guest menu browsing with strict protection outside menu scope.

**Independent Test**: Menu endpoints are public; protected endpoints require JWT/role.

### Tests for User Story 3

- [ ] T030 [P] [US3] Add menu contract tests in `tests/contract/test_menu_api.py` for categories/items with `AllowAny`.
- [ ] T031 [P] [US3] Add permission matrix tests in `tests/integration/test_permission_matrix.py` for `ROOT`/`OWNER`/`ADMIN`/`WAITER`/`COOK`/`GUEST` endpoint access.

### Implementation for User Story 3

- [ ] T032 [US3] Implement menu models in `apps/menu/models.py` for `Category` and `MenuItem` with availability and ordering fields.
- [ ] T033 [US3] Implement menu selectors in `apps/menu/selectors.py` including `get_items_by_category()` and `search_menu_items()`.
- [ ] T034 [US3] Implement menu serializers/views/urls in `apps/menu/api/{serializers.py,views.py,urls.py}` with `AllowAny` for read endpoints.
- [ ] T035 [US3] Apply role permission classes to non-menu viewsets across editor, reservations, restaurants, and orders APIs.

**Checkpoint**: Guests can browse menu; protected APIs enforce policy.

---

## Phase 6: User Story 4 - Orders Cart REST + WebSocket Sync (Priority: P2)

**Goal**: Collaborative cart with participant-restricted mutations and realtime events.

**Independent Test**: Cart REST and websocket events reflect consistent shared state.

### Tests for User Story 4

- [ ] T036 [P] [US4] Add cart contract tests in `tests/contract/test_orders_cart_api.py` for session CRUD/mutations.
- [ ] T037 [P] [US4] Add websocket integration tests in `tests/integration/test_cart_socket_events.py` for `ITEM_ADDED`, `ITEM_REMOVED`, `USER_JOINED`, `USER_LEFT`.

### Implementation for User Story 4

- [ ] T038 [US4] Implement `apps/orders/models/cart_session.py` and `apps/orders/models/cart_item.py` and expose imports via `apps/orders/models/__init__.py`.
- [ ] T039 [US4] Implement orders selectors in `apps/orders/selectors.py` (`get_cart_session()` and participant-aware fetch helpers).
- [ ] T040 [US4] Implement orders services in `apps/orders/services.py` (`create_cart_session()`, `add_item_to_cart()`, `remove_item_from_cart()`) with participant checks and service-level broadcasts.
- [ ] T041 [US4] Implement orders API v1 in `apps/orders/api/v1/{serializers.py,views.py,urls.py}` and include under `/api/orders/cart/...`.
- [ ] T042 [US4] Implement `apps/orders/consumers.py` and `apps/orders/routing.py` for `ws/cart/:session_id/`.

**Checkpoint**: Cart endpoints and socket events are functional and policy-compliant.

---

## Phase 7: User Story 5 - Restaurants/Editor Staff Operations + Hall Realtime (Priority: P3)

**Goal**: Admin/staff operational endpoints and hall status stream.

**Independent Test**: Role-scoped update endpoints and hall websocket stream work for allowed roles only.

### Tests for User Story 5

- [ ] T043 [P] [US5] Add restaurants/editor/reservation-status contract tests in `tests/contract/test_staff_ops_api.py`.
- [ ] T044 [P] [US5] Add hall websocket integration tests in `tests/integration/test_hall_socket_events.py` for `TABLE_STATUS_CHANGED` and `NEW_RESERVATION`.

### Implementation for User Story 5

- [ ] T045 [US5] Implement `apps/restaurants/models.py` restaurant entity with employee relation to user.
- [ ] T046 [US5] Implement `apps/restaurants/selectors.py` and `apps/restaurants/services.py` (`get_restaurant()`, `manage_employees()`).
- [ ] T047 [US5] Implement restaurants API in `apps/restaurants/api/{serializers.py,views.py,urls.py}` for list/update endpoints.
- [ ] T048 [US5] Implement table position update service in `apps/editor/services.py` and connect to editor API patch endpoint.
- [ ] T049 [US5] Implement `apps/editor/consumers.py` and `apps/editor/routing.py` for `ws/hall/` events.
- [ ] T050 [US5] Implement reservation status update logic in `apps/reservations/services.py` with `ROOT`/`OWNER`/`ADMIN`/`WAITER` access rules.

**Checkpoint**: Staff/admin operations and hall realtime channels are complete.

---

## Phase 8: Polish & Cross-Cutting

- [ ] T051 [P] Add seed scripts for categories/menu/tables/reservations demo data in `scripts/`.
- [ ] T052 [P] Update project docs (`README.md`, `CONTRIBUTING.md`) with new API routes, env vars, and local setup for Redis/Channels.
- [ ] T053 Run full validation: migrations, tests, flake8, bandit, safety, and fix failing checks.
- [ ] T054 Final API contract sanity check against frontend endpoints and websocket event names.

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 must complete before feature delivery work.
- Phase 2 blocks all user stories.
- US1, US2, and US3 can start after Phase 2; US4 depends on US2 and US3 data models.
- US5 can run in parallel with US4 after Phase 2, but should consume finalized permission classes.
- Phase 8 runs after desired user stories are complete.

### Parallel Opportunities

- Tasks marked `[P]` are safe for parallel execution.
- Parallel streams after foundation:
- Stream A: US1 auth implementation.
- Stream B: US2 reservation/editor API.
- Stream C: US3 menu + permission matrix.
- US4 and US5 can be split between two developers once dependencies are met.

## Notes

- Keep business rules in `services.py`; views remain orchestration-only.
- Keep complex query logic in `selectors.py`.
- Keep websocket event emission in service layer; consumers deliver transport only.
