# Feature Specification: Tablemate Backend MVP API

**Feature Branch**: `001-tablemate-backend-mvp`  
**Created**: 2026-05-07  
**Status**: Draft  
**Input**: User description: "Tablemate backend MVP with Django 5 + DRF + JWT + Google OAuth, Redis/Channels realtime flows, skinny views/fat services/selectors, and project-aligned app structure."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Authenticate via Google OAuth and JWT (Priority: P1)

As a client app, I can exchange a Google token for JWT credentials and fetch current user profile/role to access protected backend routes.

**Why this priority**: Auth is a hard dependency for all protected backend modules.

**Independent Test**: Test `google`, `refresh`, `me`, and `logout` auth endpoints in isolation.

**Acceptance Scenarios**:

1. **Given** a valid Google access token, **When** client calls `POST /api/auth/google/`, **Then** backend returns access and refresh JWT tokens plus normalized user payload.
2. **Given** a valid refresh token, **When** client calls `POST /api/auth/refresh/`, **Then** backend returns a fresh access token.
3. **Given** an authenticated JWT request, **When** client calls `GET /api/auth/me/`, **Then** backend returns current user profile including role.
4. **Given** logout request, **When** client calls `POST /api/auth/logout/`, **Then** backend invalidates token state according to JWT strategy.

---

### User Story 2 - Reserve Tables with Conflict Safety (Priority: P1)

As an authenticated user, I can check table availability and book a reservation without double booking during concurrent requests.

**Why this priority**: Reservation consistency is core business-critical behavior.

**Independent Test**: Test `available tables`, `create reservation`, and conflict responses with parallel requests.

**Acceptance Scenarios**:

1. **Given** date/time/guest filters, **When** client calls `GET /api/editor/tables/available/`, **Then** backend returns currently available tables only.
2. **Given** an available table, **When** client calls `POST /api/reservations/`, **Then** backend creates reservation and returns persisted data.
3. **Given** two simultaneous reservations for the same table/time window, **When** transaction re-check detects conflict, **Then** backend raises `ReservationConflictError` and returns HTTP 409.
4. **Given** authenticated user, **When** client calls `GET /api/reservations/my/`, **Then** backend returns only that user's reservations.

---

### User Story 3 - Browse Menu as Guest, Enforce Role Permissions Elsewhere (Priority: P1)

As a guest, I can read menu categories/items without authentication while non-menu endpoints stay protected by JWT and role permissions.

**Why this priority**: Guest menu browsing is explicit MVP requirement.

**Independent Test**: Test unauthenticated menu access and denial on protected endpoints with no token.

**Acceptance Scenarios**:

1. **Given** no auth token, **When** client calls `GET /api/menu/categories/` or `GET /api/menu/items/`, **Then** backend responds successfully (`AllowAny`).
2. **Given** no auth token, **When** client calls reservation/order/editor/restaurant protected endpoints, **Then** backend returns authorization error.
3. **Given** insufficient role token, **When** protected role-scoped endpoint is called, **Then** custom DRF permission class denies access.

---

### User Story 4 - Shared Cart with REST + WebSocket Events (Priority: P2)

As reservation participants, users can create cart sessions, mutate cart items, and receive realtime cart updates through websocket events.

**Why this priority**: Shared cart is the collaborative ordering engine.

**Independent Test**: Test cart REST endpoints and websocket `ws/cart/:session_id/` event stream together.

**Acceptance Scenarios**:

1. **Given** valid reservation, **When** client calls `POST /api/orders/cart/sessions/`, **Then** backend creates active cart session.
2. **Given** participant user, **When** client calls add/remove item endpoints, **Then** backend updates cart and emits corresponding websocket events.
3. **Given** non-participant user, **When** item mutation endpoint is called, **Then** backend denies action via service-level participant rule.
4. **Given** active cart websocket channel, **When** users join/leave or mutate items, **Then** events include `ITEM_ADDED`, `ITEM_REMOVED`, `USER_JOINED`, `USER_LEFT`.

---

### User Story 5 - Staff and Admin Operational APIs + Hall Realtime (Priority: P3)

As Admin/Waiter/Hostess roles, I can access table positioning, restaurant metadata, reservation status workflows, and live hall updates according to policy.

**Why this priority**: Operational tooling is required for staff usage but can follow core auth/reservation/cart foundation.

**Independent Test**: Test role-scoped access to editor/restaurant/reservation-status endpoints and hall websocket events.

**Acceptance Scenarios**:

1. **Given** Admin token, **When** client calls `PATCH /api/editor/tables/:id/position/`, **Then** backend updates coordinates via `editor/services.py`.
2. **Given** Waiter token, **When** client calls `PATCH /api/reservations/:id/status/`, **Then** backend allows status mutation under policy.
3. **Given** Hostess token, **When** client connects to `ws/hall/`, **Then** backend streams hall events (`TABLE_STATUS_CHANGED`, `NEW_RESERVATION`).
4. **Given** authorized restaurant staff, **When** client calls `GET /api/restaurants/` or `PATCH /api/restaurants/:id/`, **Then** backend returns/updates restaurant metadata by permission scope.

### Edge Cases

- Google token invalid/expired or audience mismatch for configured client ID.
- Refresh token revoked, malformed, or missing at `/api/auth/refresh/`.
- Reservation overlap by partial interval (e.g., intersects start/end boundaries).
- Concurrent reservation creates for same table/date/time.
- Cart item remove request targets already removed item due to concurrent participant update.
- Websocket connection attempts with unauthorized user to cart/hall channels.
- Stale JWT role claims after role update in `restaurants` employee mapping.
- Editor position patch with invalid coordinates or inactive table.
- Orders API version mismatch under `apps/orders/api/v1/` routes.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Backend MUST use Python 3.12, Django 5+, and DRF.
- **FR-002**: Backend MUST use JWT auth via `djangorestframework-simplejwt`.
- **FR-003**: Backend MUST support Google OAuth login exchange in `apps/authentication/services.py`.
- **FR-004**: Auth API MUST expose `POST /api/auth/google/`, `POST /api/auth/refresh/`, `GET /api/auth/me/`, `POST /api/auth/logout/`.
- **FR-005**: Project settings MUST follow `core/settings/base.py`, `core/settings/local.py`, `core/settings/production.py` split.
- **FR-006**: ASGI websocket entry MUST be configured through `core/asgi.py`.
- **FR-007**: Domain apps MUST include `users`, `authentication`, `restaurants`, `editor`, `reservations`, `orders`, `menu`, and shared `common`.
- **FR-008**: Domain models MUST use `UUIDMixin` and `TimestampMixin` from `common/mixins.py`.
- **FR-009**: API views MUST be skinny (routing, validation, response shaping only); business logic MUST live in services.
- **FR-010**: Complex ORM reads MUST be implemented in selectors.
- **FR-011**: Reservations service `create_reservation()` MUST re-check availability inside DB transaction before save.
- **FR-012**: Reservation conflict MUST raise `ReservationConflictError` and map to HTTP 409.
- **FR-013**: Editor API MUST expose `GET /api/editor/tables/`, `GET /api/editor/tables/available/`, `PATCH /api/editor/tables/:id/position/`.
- **FR-014**: Reservations API MUST expose `POST /api/reservations/`, `GET /api/reservations/my/`, `PATCH /api/reservations/:id/status/`.
- **FR-015**: Menu API MUST expose `GET /api/menu/categories/`, `GET /api/menu/items/`.
- **FR-016**: Menu read endpoints MUST be `AllowAny` for guest browsing.
- **FR-017**: Orders API MUST expose `POST /api/orders/cart/sessions/`, `GET /api/orders/cart/sessions/:id/`, `POST /api/orders/cart/sessions/:id/items/`, `DELETE /api/orders/cart/sessions/:id/items/:item_id/`.
- **FR-018**: Orders API implementation MUST be versioned under `apps/orders/api/v1/`.
- **FR-019**: Only cart participants may add/remove cart items.
- **FR-020**: Cart websocket broadcasts MUST be triggered from services, never views.
- **FR-021**: Restaurants API MUST expose `GET /api/restaurants/` and `PATCH /api/restaurants/:id/`.
- **FR-022**: Role permissions MUST be implemented in `common/permissions.py` (`IsAdmin`, `IsWaiter`, `IsHostess`, `IsAuthUser`).
- **FR-023**: Websocket endpoints MUST include `ws/cart/:session_id/` (orders consumer) and `ws/hall/` (editor consumer).
- **FR-024**: Cart websocket events MUST include `ITEM_ADDED`, `ITEM_REMOVED`, `USER_JOINED`, `USER_LEFT`.
- **FR-025**: Hall websocket events MUST include `TABLE_STATUS_CHANGED`, `NEW_RESERVATION`.
- **FR-026**: Environment variables MUST include `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_HOSTS`.
- **FR-027**: CI/CD workflow files MUST live under `.github/workflows/` and enforce backend quality gates.
- **FR-028**: MVP MUST exclude payments, AI features, predictive models, SMS/email notifications, and multi-restaurant support.

### Key Entities *(include if feature involves data)*

- **User** (`apps/users/models.py`): identity with unique email, profile fields, and role enum.
- **Restaurant** (`apps/restaurants/models.py`): venue metadata with employee membership relation to users.
- **Table** (`apps/editor/models.py`): hall table with position, shape, capacity, active flag, and status.
- **Reservation** (`apps/reservations/models.py`): time-bounded booking linking guest and table.
- **Category** (`apps/menu/models.py`): menu grouping with ordering semantics.
- **MenuItem** (`apps/menu/models.py`): priced dish linked to category and availability.
- **CartSession** (`apps/orders/models/cart_session.py`): active shared cart linked to reservation and participants.
- **CartItem** (`apps/orders/models/cart_item.py`): quantity entry in cart session with author and menu item linkage.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of protected endpoints reject unauthenticated access while menu read endpoints succeed for guests.
- **SC-002**: Concurrent reservation tests for same table/time result in exactly one success and one HTTP 409 conflict.
- **SC-003**: Participant authorization tests for cart mutations pass in 100% of cases.
- **SC-004**: Websocket integration tests confirm all declared cart and hall event types are emitted.
- **SC-005**: Static architecture review confirms no business-rule orchestration lives in API views for implemented modules.
- **SC-006**: CI checks in `.github/workflows/` pass lint/security/test pipeline for backend scope.

## Assumptions

- PostgreSQL is the transactional source of truth and is configured through `DATABASE_URL`.
- Redis is available for channels layer and websocket pub/sub behavior.
- Google OAuth server-side verification is available with configured `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
- Frontend clients send JWT bearer tokens for protected REST and websocket requests.
- Single-restaurant support means one active venue context for MVP (no multi-tenant/multi-restaurant behavior).
- Notification features (email/SMS) are intentionally out of scope.
