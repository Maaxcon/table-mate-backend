# Tasks: Tablemate Backend MVP API

**Input**: Design documents from `/specs/001-tablemate-backend-mvp/`
**Prerequisites**: `plan.md` (required), `spec.md` (required)
**Tests**: Included for API contracts, permissions, websocket flows, and webhook idempotency
**Organization**: Tasks grouped by user story with foundational blockers first

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: `US1..US6` mapping to spec user stories

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Align repository shape with backend constitution and target project structure.

- [ ] T001 Create settings package split by adding `core/settings/__init__.py`, `core/settings/base.py`, `core/settings/local.py`, `core/settings/production.py` and move logic from `core/settings.py`; set `AUTH_USER_MODEL` to the actual custom user model path (`<app_label>.User`, for example `authentication.User`) in `core/settings/base.py` before any `manage.py migrate` run.
- [ ] T002 [P] Add environment template updates in `.env.example` for `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_HOSTS`, `PAYMENT_WEBHOOK_SECRET`.
- [ ] T003 [P] Update dependency files `requirements/base.txt`, `requirements/dev.txt`, `requirements/prod.txt` with `djangorestframework-simplejwt`, Google token verification dependency, Redis/Channels runtime deps, and webhook signature helpers.
- [ ] T004 Create missing app skeleton `apps/users/` with `apps.py`, `models.py`, `selectors.py`, and init files.
- [ ] T004A Add bootstrap custom user model in the app that owns `User` sufficient for initial migrations, and verify configured `AUTH_USER_MODEL` resolves before first migration.
- [ ] T005 [P] Refactor orders package structure to `apps/orders/models/cart_session.py`, `apps/orders/models/cart_item.py`, `apps/orders/api/v1/{views.py,serializers.py,urls.py}` with `__init__.py` files.
- [ ] T006 [P] Add missing architecture files across apps: `services.py` and `selectors.py` in `apps/authentication`, `apps/restaurants`, `apps/editor`, `apps/reservations`, `apps/menu`, `apps/orders`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core platform behavior required before user-story work.

**CRITICAL**: No user-story implementation should start before this phase is complete.

- [ ] T007 Implement `common/mixins.py` with `UUIDMixin` and `TimestampMixin` and migrate models to use them.
- [ ] T008 Implement `common/exceptions.py` with base domain exception + `ReservationConflictError` and standard error payload mapping.
- [ ] T009 Implement role permissions in `common/permissions.py` for canonical roles `admin`, `waiter`, `cook`, `customer`.
- [ ] T010 Configure DRF + JWT in `core/settings/base.py` with `simplejwt` authentication and default permission policy.
- [ ] T011 Configure Channels + Redis layer in `core/settings/base.py` and websocket entry in `core/asgi.py`.
- [ ] T012 Update root routing in `core/urls.py` and `core/routing.py` for API includes and websocket routes (`ws/cart/:session_id/`, `ws/hall/`).
- [ ] T013 Add backend quality gates to `.github/workflows/main.yml` for lint/security/tests (`flake8`, `bandit`, `safety`, test suite).

**Checkpoint**: Architecture, auth infrastructure, role policy, and routing foundation are ready for feature implementation.

---

## Phase 3: User Story 1 - Google OAuth + JWT Auth (Priority: P1)

**Goal**: Complete token exchange and identity endpoints.

**Independent Test**: Auth endpoints work end-to-end with valid and invalid tokens.

### Tests for User Story 1

- [ ] T014 [P] [US1] Add auth API contract tests in `tests/contract/test_auth_api.py` for `/api/auth/google/`, `/api/auth/refresh/`, `/api/auth/me/`, `/api/auth/logout/`.
- [ ] T015 [P] [US1] Add auth integration tests in `tests/integration/test_google_jwt_flow.py` for success/failure paths.

### Implementation for User Story 1

- [ ] T016 [US1] Extend bootstrap `apps/users/models.py` custom `User` model with UUID PK, unique email, profile fields, and role enum (`admin/waiter/cook/customer`).
- [ ] T017 [US1] Implement `apps/users/selectors.py` with `get_user_by_email()` and helper lookup functions.
- [ ] T018 [US1] Implement `apps/authentication/services.py` Google verification and JWT issuance workflow.
- [ ] T019 [US1] Implement auth serializers and views in `apps/authentication/api/serializers.py` and `apps/authentication/api/views.py`.
- [ ] T020 [US1] Wire auth URLs in `apps/authentication/api/urls.py` and include from `core/urls.py`.
- [ ] T021 [US1] Add logout token invalidation strategy and stale-role token rejection in auth service layer.

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

**Goal**: Public menu browsing with strict protection outside menu scope.

**Independent Test**: Menu endpoints are public; protected endpoints require JWT/role.

### Tests for User Story 3

- [ ] T030 [P] [US3] Add menu contract tests in `tests/contract/test_menu_api.py` for categories/items with `AllowAny`.
- [ ] T031 [P] [US3] Add permission matrix tests in `tests/integration/test_permission_matrix.py` for `admin`/`waiter`/`cook`/`customer` endpoint access.

### Implementation for User Story 3

- [ ] T032 [US3] Implement menu models in `apps/menu/models.py` for top-level `Menu`, `Category`, and `MenuItem` with availability and ordering fields.
- [ ] T033 [US3] Implement menu selectors in `apps/menu/selectors.py` including top-level menu lookup, `get_items_by_category()`, and `search_menu_items()`.
- [ ] T034 [US3] Implement menu serializers/views/urls in `apps/menu/api/{serializers.py,views.py,urls.py}` with `AllowAny` for read endpoints.
- [ ] T035 [US3] Apply role permission classes to non-menu views across editor, reservations, restaurants, and orders APIs.

**Checkpoint**: Guests can browse menu; protected APIs enforce canonical staff role policy.

---

## Phase 6: User Story 4 - Orders Cart REST + WebSocket Sync (Priority: P2)

**Goal**: Collaborative cart with participant-restricted mutations and realtime events.

**Independent Test**: Cart REST and websocket events reflect consistent shared state.

### Tests for User Story 4

- [ ] T036 [P] [US4] Add cart contract tests in `tests/contract/test_orders_cart_api.py` for session CRUD/mutations.
- [ ] T037 [P] [US4] Add websocket integration tests in `tests/integration/test_cart_socket_events.py` for `CART_ITEM_ADDED`, `CART_ITEM_REMOVED`, `CART_PARTICIPANT_JOINED`, `CART_PARTICIPANT_LEFT`.

### Implementation for User Story 4

- [ ] T038 [US4] Implement `apps/orders/models/cart_session.py` and `apps/orders/models/cart_item.py` and expose imports via `apps/orders/models/__init__.py`.
- [ ] T039 [US4] Implement orders selectors in `apps/orders/selectors.py` (`get_cart_session()` and participant-aware fetch helpers).
- [ ] T040 [US4] Implement orders services in `apps/orders/services.py` (`create_cart_session()`, `add_item_to_cart()`, `remove_item_from_cart()`) with participant checks and service-level broadcasts.
- [ ] T041 [US4] Implement orders API v1 in `apps/orders/api/v1/{serializers.py,views.py,urls.py}` and include under `/api/orders/cart/...`.
- [ ] T042 [US4] Implement `apps/orders/consumers.py` and `apps/orders/routing.py` for `ws/cart/:session_id/`.

**Checkpoint**: Cart endpoints and socket events are functional and policy-compliant.

---

## Phase 7: User Story 5 - Staff Operations + Hall Realtime (Priority: P2)

**Goal**: Staff operational endpoints and hall status stream.

**Independent Test**: Role-scoped update endpoints and hall websocket stream work for allowed roles only.

### Tests for User Story 5

- [ ] T043 [P] [US5] Add restaurants/editor/reservation-status contract tests in `tests/contract/test_staff_ops_api.py`.
- [ ] T044 [P] [US5] Add hall websocket integration tests in `tests/integration/test_hall_socket_events.py` for `HALL_TABLE_STATUS_CHANGED` and `HALL_NEW_RESERVATION`.

### Implementation for User Story 5

- [ ] T045 [US5] Implement `apps/restaurants/models.py` with `Restaurant` plus one-to-one `RestaurantSettings` (`timezone`, `currency`, `locale`, `working_hours`, `default_tax_rate`) and employee relation to user.
- [ ] T046 [US5] Implement `apps/restaurants/selectors.py` and `apps/restaurants/services.py` (`get_restaurant()`, `get_restaurant_settings()`, `manage_employees()`).
- [ ] T047 [US5] Implement restaurants API in `apps/restaurants/api/{serializers.py,views.py,urls.py}` for list/update endpoints.
- [ ] T048 [US5] Implement table position update service in `apps/editor/services.py` and connect to editor API patch endpoint.
- [ ] T049 [US5] Implement `apps/editor/consumers.py` and `apps/editor/routing.py` for `ws/hall/` events.
- [ ] T050 [US5] Implement reservation status update logic in `apps/reservations/services.py` with `admin`/`waiter` access rules and explicit denial for `customer`/`cook`.

**Checkpoint**: Staff operations and hall realtime channels are complete.

---

## Phase 8: User Story 6 - Payment Confirmation via Trusted Webhook (Priority: P1)

**Goal**: Accept payment confirmation only through trusted webhook and apply paid+ticket side effects exactly once.

**Independent Test**: Valid signature triggers atomic transition; invalid signature rejected; duplicate webhook is idempotent.

### Tests for User Story 6

- [ ] T051 [P] [US6] Add payment webhook contract tests in `tests/contract/test_payment_webhook_api.py`.
- [ ] T052 [P] [US6] Add idempotency integration tests in `tests/integration/test_payment_webhook_idempotency.py`.

### Implementation for User Story 6

- [ ] T053 [US6] Implement webhook endpoint in `apps/orders/api/v1/views.py` with signature verification.
- [ ] T054 [US6] Implement webhook service in `apps/orders/services.py` for atomic payment confirmation + ticket injection.
- [ ] T055 [US6] Persist immutable payment records in `apps/orders/models.py` (or dedicated payment model module).
- [ ] T056 [US6] Emit `PAYMENT_CONFIRMED` and `KITCHEN_TICKET_INJECTED` events with `schema_version` and dedup keys.
- [ ] T057 [US6] Ensure duplicate provider event id is deduplicated and side effects are not replayed.
- [ ] T062 [US6] Source payment and `PAYMENT_CONFIRMED.currency` from `RestaurantSettings.currency` in webhook processing and event payload mapping.

**Checkpoint**: Webhook authority and idempotent payment transition are complete.

---

## Phase 9: Polish & Cross-Cutting

- [ ] T058 [P] Add seed scripts for menus/categories/items, restaurant settings, tables, and reservations demo data in `scripts/`.
- [ ] T059 [P] Update project docs (`README.md`, `CONTRIBUTING.md`) with new API routes, env vars, and local setup for Redis/Channels.
- [ ] T060 Run full validation: migrations, tests, flake8, bandit, safety, and fix failing checks.
- [ ] T061 Final API contract sanity check against frontend endpoints and websocket event names.
- [ ] T063 Add DB migrations for hot-path indexes: `Ticket(restaurant, status, injected_at)`, `OrderItem(restaurant, status, menu_item)`, and partial `Session(restaurant, table_id) WHERE status='open'`.
- [ ] T064 [P] Add integration/query-plan checks in `tests/integration/test_hot_path_indexes.py` to verify hot-path queries use declared indexes.

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 must complete before feature delivery work.
- Phase 2 blocks all user stories.
- US1, US2, and US3 can start after Phase 2.
- US4 depends on US2 and US3 data models.
- US5 can run in parallel with US4 after permission layer is stable.
- US6 depends on order/ticket lifecycle readiness (US4) and role/event foundation from Phase 2.
- Phase 9 runs after desired user stories are complete.

### Parallel Opportunities

- Tasks marked `[P]` are safe for parallel execution.
- Parallel streams after foundation:
- Stream A: US1 auth implementation.
- Stream B: US2 reservation/editor API.
- Stream C: US3 menu + permission matrix.
- Stream D: US4 websocket/event transport.
- Stream E: US6 webhook and idempotency tests after US4 readiness.

## Notes

- Keep business rules in `services.py`; views remain orchestration-only.
- Keep complex query logic in `selectors.py`.
- Keep websocket and webhook side effects emitted by services with typed/versioned contracts.
