# Feature Specification: Tablemate Backend MVP API

**Feature Branch**: `001-tablemate-backend-mvp`
**Created**: 2026-05-07
**Updated**: 2026-05-12
**Status**: Finalized
**Input**: User description: "Tablemate backend MVP with Constitution v2.0.0 alignment for roles, realtime contracts, webhook authority, immutable boundaries, canonical entities, and hot-path indexing."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Authenticate with Google and Role-Scoped JWT (Priority: P1)

As a client app, I can exchange a Google token for JWT credentials and fetch the current profile so protected routes are accessed with backend-authorized identity.

**Why this priority**: Authentication and role claims are prerequisites for all protected flows.

**Independent Test**: Validate Google exchange, refresh, profile lookup, logout, and stale-role-token invalidation behavior.

**Acceptance Scenarios**:

1. **Given** a valid Google access token, **When** client calls `POST /api/auth/google/`, **Then** backend returns access/refresh credentials and normalized user profile with role.
2. **Given** a valid refresh token, **When** client calls `POST /api/auth/refresh/`, **Then** backend issues a new access token.
3. **Given** an authenticated request, **When** client calls `GET /api/auth/me/`, **Then** backend returns current profile and effective role.
4. **Given** a staff role update, **When** previously issued tokens are used, **Then** backend rejects stale tokens and requires re-authentication.

---

### User Story 2 - Reserve Tables with Conflict Safety (Priority: P1)

As a customer, I can check table availability and create a reservation without double-booking under concurrent requests.

**Why this priority**: Reservation consistency is core operational behavior.

**Independent Test**: Execute parallel reservation attempts for the same table/time window and verify exactly one success.

**Acceptance Scenarios**:

1. **Given** date/time/guest filters, **When** client calls `GET /api/editor/tables/available/`, **Then** backend returns only currently available tables.
2. **Given** an available table, **When** client calls `POST /api/reservations/`, **Then** backend stores reservation and returns persisted details.
3. **Given** two simultaneous reservation requests for the same table/time window, **When** backend re-checks availability in transaction, **Then** one request succeeds and the conflicting request returns HTTP 409.
4. **Given** authenticated customer, **When** client calls `GET /api/reservations/my/`, **Then** backend returns only that customer’s reservations.

---

### User Story 3 - Public Menu and Protected Operations (Priority: P1)

As a customer, I can browse menu data without authentication while protected operational endpoints remain guarded by JWT and role policy.

**Why this priority**: Public menu visibility is required while operational APIs must remain protected.

**Independent Test**: Verify unauthenticated access to menu endpoints and authorization denial on protected endpoints.

**Acceptance Scenarios**:

1. **Given** no auth token, **When** client calls `GET /api/menu/categories/` and `GET /api/menu/items/`, **Then** backend returns menu data successfully.
2. **Given** no auth token, **When** client calls protected reservation/order/editor/restaurant endpoints, **Then** backend returns authorization error.
3. **Given** authenticated staff with insufficient permissions, **When** restricted endpoint is called, **Then** backend denies the action according to role matrix.

---

### User Story 4 - Shared Cart with Live WebSocket Updates (Priority: P2)

As reservation participants, users can mutate a shared cart and receive realtime updates through backend-originated WebSocket events.

**Why this priority**: Shared cart collaboration depends on deterministic live updates.

**Independent Test**: Validate cart REST mutations together with WebSocket event delivery, replay, and idempotent handling.

**Acceptance Scenarios**:

1. **Given** a valid reservation, **When** client calls `POST /api/orders/cart/sessions/`, **Then** backend creates an active cart session.
2. **Given** a cart participant, **When** item add/remove endpoints are called, **Then** backend applies mutation and emits cart events.
3. **Given** a non-participant, **When** item mutation endpoint is called, **Then** backend denies mutation.
4. **Given** reconnect after disconnection, **When** client provides replay cursor, **Then** backend replays missed events for the session window.

---

### User Story 5 - Staff Operations and Hall Realtime (Priority: P2)

As users with roles (`admin`, `waiter`, `cook`, `customer`), I can access only role-allowed operations; customer role is denied staff-only hall and operational actions.

**Why this priority**: Safe staff operations require strict backend role enforcement.

**Independent Test**: Validate role-scoped access for restaurants/editor/reservation-status routes and hall stream behavior.

**Acceptance Scenarios**:

1. **Given** `admin` role, **When** restaurant management endpoints are called, **Then** backend allows admin-level operations.
2. **Given** `customer` role, **When** staff operational endpoints are called, **Then** backend denies the action.
3. **Given** `waiter` role, **When** reservation status update endpoint is called, **Then** backend applies allowed status transitions.
4. **Given** `cook` role, **When** kitchen workflow endpoints are called, **Then** backend allows kitchen-only order item updates.
5. **Given** authorized hall subscriber, **When** table/reservation state changes, **Then** backend emits hall events with declared schema version.

---

### User Story 6 - Payment Confirmation via Trusted Webhook (Priority: P1)

As the operations platform, payment confirmation is accepted only from a verified provider webhook, and paid orders are injected into kitchen flow atomically.

**Why this priority**: Constitution v2.0.0 requires trusted webhook authority for payment state.

**Independent Test**: Verify signature validation, idempotent duplicate webhook handling, and atomic paid+ticket injection behavior.

**Acceptance Scenarios**:

1. **Given** a valid signed payment webhook, **When** backend processes callback, **Then** order transitions from `unpaid` to `paid`, kitchen ticket is created, and events are broadcast.
2. **Given** invalid webhook signature, **When** callback is received, **Then** backend rejects request and no order state change occurs.
3. **Given** duplicate delivery of same webhook event, **When** backend processes retries, **Then** payment transition side effects are applied exactly once.

### Edge Cases

- Google token is expired, invalid, or for a mismatched client audience.
- Refresh token is revoked, malformed, or missing.
- Reservation intervals overlap at boundaries or during high concurrency.
- Cart removal is requested for an item already removed by another participant.
- Unauthorized WebSocket connection attempts occur for cart/hall channels.
- Event replay cursor is stale or points before retention window.
- Unsupported `schema_version` is received by a consumer.
- Duplicate payment webhook deliveries arrive out of order.
- Webhook signature is missing or invalid.
- Staff role changes while existing staff tokens are still active.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Backend MUST use Python 3.12, Django 5+, and DRF.
- **FR-002**: Backend MUST use JWT authentication.
- **FR-003**: Backend MUST support Google OAuth exchange for sign-in.
- **FR-004**: Auth API MUST expose `POST /api/auth/google/`, `POST /api/auth/refresh/`, `GET /api/auth/me/`, and `POST /api/auth/logout/`.
- **FR-005**: Settings MUST be split into base/local/production configuration files.
- **FR-006**: ASGI entry MUST be configured for REST + WebSocket runtime.
- **FR-007**: Domain apps MUST include users, authentication, restaurants, editor, reservations, orders, menu, payments, and shared common layer.
- **FR-008**: Domain models MUST use shared UUID and timestamp mixins.
- **FR-009**: API views MUST stay orchestration-only; business rules MUST be implemented in services.
- **FR-010**: Complex read queries MUST be implemented in selectors.
- **FR-011**: Reservation creation MUST re-check availability inside database transaction before persistence.
- **FR-012**: Reservation conflicts MUST return HTTP 409.
- **FR-013**: Editor API MUST expose table list, available tables, and table position update endpoints.
- **FR-014**: Reservations API MUST expose create, self-list, and status update endpoints.
- **FR-015**: Menu API MUST expose categories and items read endpoints.
- **FR-016**: Menu read endpoints MUST allow unauthenticated access.
- **FR-017**: Orders API MUST expose cart session create/get, item add, and item remove endpoints.
- **FR-018**: Orders API MUST remain versioned.
- **FR-019**: Only cart participants MAY mutate cart contents.
- **FR-020**: Cart and hall WebSocket broadcasts MUST be emitted from service layer, not views.
- **FR-021**: Restaurants API MUST expose list and update endpoints under role policy.
- **FR-022**: Authorization MUST enforce canonical roles only: `admin`, `waiter`, `cook`, `customer`.
- **FR-023**: WebSocket endpoints MUST include cart session channel and hall channel.
- **FR-024**: Cart events MUST include item add/remove and participant join/leave event types.
- **FR-025**: Hall events MUST include table status and reservation creation event types.
- **FR-026**: Required environment variables MUST include `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_HOSTS`, and payment webhook secret.
- **FR-027**: CI workflows MUST enforce lint, security, and automated tests.
- **FR-028**: MVP MUST exclude AI features, predictive models, SMS/email notifications, and multi-restaurant support.
- **FR-029**: Payment confirmation MUST be accepted only through provider webhook after signature validation.
- **FR-030**: Order payment status transition `unpaid -> paid` MUST be performed only by webhook processing.
- **FR-031**: Successful payment webhook processing MUST atomically apply: payment confirmation, kitchen ticket injection, and event publication intent.
- **FR-032**: Duplicate webhook deliveries MUST be idempotent and MUST NOT duplicate payment-side effects.
- **FR-033**: Event contracts MUST include typed names, audience, required payload fields, and `schema_version`.
- **FR-034**: Event delivery MUST be at-least-once with reconnect replay for missed session events.
- **FR-035**: Unsupported event versions MUST be ignored safely by consumers and logged for observability.
- **FR-036**: Staff role change MUST invalidate active staff tokens immediately.
- **FR-037**: Session close MUST be explicit waiter action; backend inactivity timeout MUST NOT auto-close sessions.
- **FR-038**: Financial write operations MUST be internal-only; external APIs are read-only for financial data.
- **FR-039**: Immutable boundaries MUST be enforced for closed sessions, settled orders, finalized tickets, payment records, and reporting snapshots.
- **FR-040**: `RestaurantSettings` MUST exist as a one-to-one sibling of `Restaurant` and include `timezone`, `currency`, `locale`, `working_hours`, `default_tax_rate`, and `default_service_charge`.
- **FR-041**: Menu domain MUST include top-level `Menu` entity (for example breakfast/lunch/dinner) with category/item associations.
- **FR-042**: Payment and payment-derived event currency (including `PAYMENT_CONFIRMED.currency`) MUST be sourced from `RestaurantSettings.currency`.
- **FR-043**: Backend hot read paths MUST be indexed with `Ticket(restaurant, status, injected_at)`, `OrderItem(restaurant, status, menu_item)`, and partial index `Session(restaurant, table_id) WHERE status='open'`.
- **FR-044**: `AUTH_USER_MODEL` MUST be set in `core/settings/base.py` to the actual custom user model path (`<app_label>.User`, for example `authentication.User`) before the first `manage.py migrate`; auth model swapping after initial migration is out of scope and forbidden for MVP rollout.
- **FR-045**: Custom `User` model MUST use `AbstractBaseUser + PermissionsMixin` with email as `USERNAME_FIELD` (no required username field).
- **FR-046**: Role/status enums MUST use Django `models.TextChoices` (not plain Python enums) across the codebase, including `order`, `order_item`, `ticket`, and `session` status fields. `Table` has no stored `status` field — occupancy is derived from `Session`.
- **FR-047**: Provider webhook endpoints MUST live in a dedicated `payments` app (signature-authenticated callback surface) and MUST NOT be mixed into customer-facing orders REST endpoints.
- **FR-048**: Payments persistence MUST use dedicated models in `apps/payments`: `Payment(order, provider, provider_transaction_id UNIQUE, amount, currency, status, raw_payload jsonb)` and `WebhookEvent(provider, event_id UNIQUE, payload, received_at, processed_at)` as required idempotency primitives for FR-032.
- **FR-049**: OpenAPI/TypeScript contract pipeline MUST be foundational: backend MUST generate validated schema (`manage.py spectacular --validate --file schema.yaml`) and CI MUST fail on contract drift; frontend type generation MUST consume this schema.
- **FR-050**: Void reason master data MUST be seeded with exactly: `mispick`, `guest_changed_mind`, `quality_issue`, `out_of_stock`.
- **FR-051**: `Order` and `OrderItem` MUST include tax/discount/tip columns with default `0`, including per-line tax support for receipt-grade breakdowns.
- **FR-052**: Foreign-key `on_delete` policies MUST be explicit; minimum protections: `OrderItem.menu_item -> PROTECT` and all `*.restaurant -> PROTECT`.
- **FR-053**: Dependency manifest MUST include `djangorestframework-simplejwt`, Google token verification dependency, and `drf-spectacular`; for this repository, `pyproject.toml`/`uv.lock` are the authoritative equivalent of `requirements/base.txt`.

### Canonical Contract Impact

- **Impacted Entities**: Restaurant, RestaurantSettings, Menu, Table, Reservation, Order, OrderItem, Ticket, Session, Staff, Payment, WebhookEvent, SessionSnapshot.
- **Contract Delta**: Adds explicit webhook-confirmed payment transitions, replay cursor semantics for live events, immutable lifecycle boundaries for finalized records, canonical currency source (`RestaurantSettings.currency`), required payment/webhook idempotency primitives (`Payment` + `WebhookEvent` unique keys), foundational contract-generation/type-sync gate, and hot-path indexing requirements.
- **Backward Compatibility**: Existing event fields remain stable within active `schema_version`; new optional fields are additive.
- **Backend Source of Truth Rule**: Canonical state transitions are accepted only through backend service operations and confirmed by backend event broadcast.

### Role Access Matrix

- **admin**: Full operational access including restaurant management, staff management, layout publishing, and financial reporting.
- **admin restricted**: None inside backend MVP operational scope.
- **waiter**: Table/hall operations, reservation handling, session close action, and customer order support.
- **waiter restricted**: No financial administration, no staff management, no kitchen-only item lifecycle operations.
- **cook**: Kitchen queue and order item preparation lifecycle updates.
- **cook restricted**: No floor-plan editing, no reservation creation, no financial operations.
- **customer**: Menu browsing, reservation create/list-own, and cart participation.
- **customer restricted**: No staff operational endpoints, no hall monitoring, no kitchen lifecycle actions, no financial/staff management operations.

### Event Catalog (Mandatory)

| Event Name | schema_version | Producer | Consumer | Required Payload Fields | Replay Behavior | Idempotency / Dedup Rule |
|---|---|---|---|---|---|---|
| `CART_ITEM_ADDED` | `1` | Cart service | Cart participants | `event_id`, `session_id`, `item_id`, `menu_item_id`, `quantity`, `actor_id`, `occurred_at` | Replay if newer than client cursor and inside retention window | Deduplicate by `event_id`; ignore duplicates |
| `CART_ITEM_REMOVED` | `1` | Cart service | Cart participants | `event_id`, `session_id`, `item_id`, `actor_id`, `occurred_at` | Replay on reconnect within retention | Deduplicate by `event_id` |
| `CART_PARTICIPANT_JOINED` | `1` | Cart presence service | Cart participants | `event_id`, `session_id`, `user_id`, `occurred_at` | Replay within retention for missed presence transitions | Deduplicate by `event_id` |
| `CART_PARTICIPANT_LEFT` | `1` | Cart presence service | Cart participants | `event_id`, `session_id`, `user_id`, `occurred_at` | Replay within retention for missed presence transitions | Deduplicate by `event_id` |
| `HALL_TABLE_STATUS_CHANGED` | `1` | Table state service | Hall subscribers (staff) | `event_id`, `table_id`, `previous_status`, `current_status`, `session_id`, `actor_id`, `actor_role`, `occurred_at` | Replay if change occurred after cursor | Deduplicate by `event_id`; `current_status` is derived (`free` when no open `Session` exists for the table, `occupied` when an open `Session` exists) — `Table` model has no stored `status` column |
| `HALL_NEW_RESERVATION` | `1` | Reservation service | Hall subscribers (staff) | `event_id`, `reservation_id`, `table_id`, `start_at`, `end_at`, `actor_id`, `occurred_at` | Replay within retention to restore hall timeline | Deduplicate by `event_id` |
| `PAYMENT_CONFIRMED` | `1` | Payment webhook service | waiter and kitchen channels | `event_id`, `provider_event_id`, `order_id`, `payment_status`, `amount`, `currency`, `occurred_at` | Replay for subscribers that missed confirmation | Deduplicate by `provider_event_id` |
| `KITCHEN_TICKET_INJECTED` | `1` | Ticket injection service | Kitchen channel | `event_id`, `ticket_id`, `order_id`, `injected_at`, `priority`, `occurred_at` | Replay for disconnected kitchen clients | Deduplicate by `event_id` |
| `ORDER_ITEM_STATUS_CHANGED` | `1` | Kitchen workflow service | waiter and kitchen channels | `event_id`, `order_item_id`, `previous_status`, `current_status`, `actor_id`, `actor_role`, `occurred_at` | Replay after cursor within retention | Deduplicate by `event_id` |
| `SESSION_CLOSED` | `1` | Session lifecycle service | waiter and admin channels | `event_id`, `session_id`, `table_id`, `closed_by`, `snapshot_id`, `occurred_at` | Replay close notifications for disconnected staff | Deduplicate by `event_id` |

`PAYMENT_CONFIRMED.currency` source of truth is `RestaurantSettings.currency` for the order's restaurant.

### Replay Semantics

- Event delivery guarantee is at-least-once per connected client session.
- Each event includes immutable `event_id`, `schema_version`, and `occurred_at` fields.
- Clients reconnect with last processed cursor; backend replays only events newer than that cursor within configured retention window.
- Consumers MUST be idempotent and deduplicate using event-level key specified in event catalog.
- Ordering assumption: strict ordering is guaranteed only within a single stream key (for example per `session_id` or per `ticket_id`).
- If consumer receives unsupported `schema_version`, consumer MUST ignore the event payload for state mutation and log unsupported version occurrence.
- Version compatibility policy is additive-first: existing fields are not removed from active versions during the deprecation window.

### Authoritative State Transitions

| Transition Domain | Authoritative Backend Service | Allowed Transition Rule | Client Restriction |
|---|---|---|---|
| Table status | Table state service (derived from `Session`) | `free` = no open `Session` for table; `occupied` = open `Session` exists. Transitions occur on session open/close — no stored `status` column on `Table` | Clients MAY request; clients MUST NOT set canonical table status directly |
| Session lifecycle | Session lifecycle service | Open on waiter manual flow or prepaid confirmation; close only on explicit waiter close action | No client-side auto-close or timeout-driven canonical close |
| Order lifecycle | Order orchestration service | `draft -> submitted -> unpaid -> paid -> settled` with policy checks | Clients cannot mark paid/settled directly |
| Order item lifecycle | Kitchen workflow service | `pending -> in_progress -> ready -> served` and void branch by policy | Frontend cannot bypass kitchen policy or set terminal status directly |
| Kitchen ticket creation | Ticket injection service | Ticket created only from successful paid order transition | No direct client endpoint for ticket injection |
| Payment status | Payment webhook service | `unpaid -> paid` only after signature-validated provider webhook | Client/staff endpoints cannot confirm payment |
| Void/refund | Void and refund service | Transactional void/refund with audit trail and correction records | No direct client-side mutation of finalized financial state |

Frontend applications may request actions but MUST NOT perform authoritative business state transitions.

### Immutable Boundaries

| Record Type | Becomes Immutable At | Allowed Changes After Boundary |
|---|---|---|
| Completed session | Session close confirmation and snapshot creation | No mutable field updates; only append-only correction records with audit linkage |
| Settled order | Transition to `settled` | No direct edits to order totals/items; adjustments require separate audited compensation flow |
| Payment record | Successful webhook confirmation persisted | No update/delete via external API; append-only reconciliation metadata only |
| Kitchen ticket | Dispatch to kitchen or completion | No field mutation of dispatched/completed ticket; cancellation uses separate cancellation record |
| Reporting snapshot / audit log | Snapshot write completion | Fully immutable; corrections stored as new records, never in-place overwrite |

### Key Entities *(include if feature involves data)*

- **User**: Account identity with role-scoped authorization context. Role (`admin`/`waiter`/`cook`/`customer`) is a direct attribute on `User`; a separate `RoleAssignment` entity is not used in MVP.
- **Restaurant**: Venue metadata, active floor-plan reference, and staff membership relation.
- **RestaurantSettings**: One-to-one restaurant settings entity carrying `timezone`, `currency`, `locale`, `working_hours`, `default_tax_rate`, and `default_service_charge`.
- **Table**: Hall table identity, position, and capacity. Occupancy state is derived — a table is `occupied` when an open `Session` exists for it, `free` otherwise. No stored `status` column.
- **Reservation**: Time-bounded customer booking linked to table.
- **Menu**: Top-level menu container per restaurant (for example breakfast/lunch/dinner).
- **MenuCategory**: Grouping entity for menu organization within a menu.
- **MenuItem**: Orderable dish with availability and price metadata within a menu/category.
- **CartSession**: Shared ordering context linked to reservation participants.
- **CartItem**: Item entry within cart session.
- **Order**: Confirmed customer order with payment lifecycle.
- **OrderItem**: Individual kitchen-trackable line item with lifecycle state and per-line financial fields for receipt/tax breakdowns.
- **KitchenTicket**: Kitchen projection created from confirmed paid order.
- **Payment**: Provider transaction record with unique `provider_transaction_id`, payment amount/currency/status, and raw payload retention.
- **WebhookEvent**: Immutable inbound webhook event record with unique provider `event_id`, payload, and processing timestamps.
- **SessionSnapshot**: Immutable analytics snapshot created at session close.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of protected operational endpoints reject unauthorized access while public menu endpoints remain accessible without login.
- **SC-002**: Concurrent reservation conflict tests for same table/time produce exactly one success and one conflict response.
- **SC-003**: 100% of duplicate payment webhook retries produce no duplicate paid transitions or duplicate kitchen ticket injections.
- **SC-004**: Reconnect tests confirm missed realtime events are replayed within retention and processed without duplicate side effects.
- **SC-005**: Role-matrix verification confirms `admin`/`waiter`/`cook`/`customer` boundaries are enforced on all scoped endpoints.
- **SC-006**: Closed sessions, settled orders, payment records, and reporting snapshots remain immutable in all post-settlement test scenarios.
- **SC-007**: Quality and security validation gates pass before release readiness review.
- **SC-008**: Hot-path queries for incoming tickets, kitchen batch items, and open table sessions use declared composite/partial indexes in production query plans.

## Assumptions

- Single restaurant context remains active for MVP; multi-restaurant tenancy is deferred.
- Payment provider sends signed webhook events with stable provider event identifiers.
- Clients can persist and send replay cursors for reconnect recovery.
- Event retention window is sufficient for normal short-lived disconnections.
- Frontend consumes backend event contracts and does not apply local authoritative state transitions.
