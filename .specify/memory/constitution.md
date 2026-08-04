<!--
Sync Impact Report
- Version change: 2.0.1 -> 2.1.0
- Modified principles:
  - None
- Modified sections:
  - Foundation Contracts / Canonical Entity Definitions: added `Shift`,
    `Receipt`, `ReceiptItem`, `CartSession`, `CartItem`, `GuestProfile`,
    `VoidReason`, `Payment`, `WebhookEvent` entities that were built but
    undocumented. Removed outdated note that shift-status tracking was "out
    of MVP scope" (shifts app now exists). Updated `Session` to reflect
    auto-extend and grace-period close behavior.
  - Foundation Contracts / Role Access Matrix: added shift-management
    access for `admin` role.
  - Foundation Contracts / Payment Contract: removed unsupported payment
    providers clause; current implementation simulates payment via direct
    marking (webhook path is skeletal).
  - Foundation Contracts / Event Catalog: normative content was already
    in spec.md, not constitution; removed placeholder reference.
  - Backend Constitution / VI, IX: clarified auto-extend and grace-period
    close as backend-managed (human-initiated close is primary, auto-close
    acts as safety net with grace window).
- Added sections:
  - Foundation Contracts / Walk-In Contract: walk-in reservation flow.
  - Foundation Contracts / Receipt Contract: immutable cabinet receipt.
  - Foundation Contracts / Cart Session Contract: ephemeral shared cart.
  - Foundation Contracts / Shift Management Contract: staff scheduling.
  - Foundation Contracts / Staff Notification Contract: notification store.
  - Backend Constitution / XI. Async Task Infrastructure: Celery.
  - Backend Constitution / XII. Notification Store: Redis-backed.
  - Backend Constitution / XIII. Walk-In Flow: guest flow.
  - Backend Constitution / XIV. Receipt Snapshot: cabinet history.
  - Backend Constitution / XV. Cart Session Lifecycle: shared cart.
  - Backend Constitution / XVI. Service Layer Organization: services/ split.
- Removed sections:
  - None
- Templates requiring updates:
  - ✅ .specify/templates/plan-template.md (no changes required)
  - ✅ .specify/templates/spec-template.md
  - ✅ .specify/templates/tasks-template.md
- Deferred TODOs:
  - Payment webhook proper implementation (US6 from MVP spec): needs
    services.py, webhooks.py, api/v1/, signature validation, idempotency.
  - Void flow atomic transaction per Void Contract (currently void_order_item
    is a single update, not a full atomic transaction with rollback).
  - Hot-path DB indexes per FR-043.
-->

# TableMate Platform Constitution

## Core Principles

### I. Right Role, Right Moment, Zero Ambiguity
TableMate MUST deliver authoritative information to each role with no ambiguity
and no avoidable delay. Latency and inconsistency are functional defects,
including stale floor state, delayed kitchen updates, and delayed financial
visibility.

Rationale: service operations fail when truth arrives late or differs by
surface.

### II. Canonical Shared Data Contracts
Frontend and backend MUST use one canonical contract for shared entities.
Role-specific local variants of canonical entities are forbidden.

Rationale: divergent entity shapes create silent operational drift.

### III. Role-Scoped Access Is Structural and Enforced
Backend MUST enforce role permissions on every request and event audience.
Frontend MUST structurally omit inaccessible routes and components from the
render tree; hiding is insufficient.

Rationale: true least-privilege requires both server enforcement and client
structure.

### IV. Live State Is WebSocket-Delivered, Typed, and Versioned
Live state MUST be delivered by WebSocket only. REST MUST be limited to create
and mutate operations. Events MUST be typed, versioned, and audience-scoped.
Clients MUST ignore unknown event versions safely.

Rationale: deterministic live delivery is required for kitchen and floor timing.

### V. Critical Transactions Are Backend-Atomic
Critical transitions (payment confirmation, void execution, and session-close
financial impact) MUST be executed as backend-controlled atomic transactions
with explicit rollback behavior.

Rationale: partial updates corrupt kitchen, receipt, and revenue truth.

## Foundation Contracts

### Canonical Entity Definitions
The following entities are the source of truth across all surfaces:

- `Restaurant`: `id`, `name`, active floor-plan reference, QR mappings to table
  IDs.
- `RestaurantSettings`: one-to-one sibling of `Restaurant` (`restaurant_id`);
  `timezone`, `currency`, `locale`, `working_hours`, `default_tax_rate`,
  `default_service_charge`.
- `Table`: `id`, sector, capacity, and status (`free`, `occupied`).
  Status is backend-computed and backend-pushed only. No stored `status`
  column — occupancy is derived from open `Session` existence.
- `Menu`: top-level menu container for a restaurant (for example breakfast,
  lunch, dinner) with `id`, restaurant reference, `name`, service window
  metadata, active flag, and menu item/category associations.
- `Order`: `id`, table reference, session reference, origin
  (`waiter_manual`, `customer_prepaid`), payment status
  (`unpaid`, `paid`, `settled`, `cancelled`), tax/service/tip totals, and
  `OrderItem[]`.
- `OrderItem`: `id`, menu item reference, quantity, modifier text, guest slot
  index, lifecycle status (`pending`, `in_progress`, `ready`, `voided`,
  `served`), per-line financial fields (`unit_price`, `total_price`,
  `tax_amount`, `service_charge_amount`), and void audit trail (`voided_at`,
  `voided_by`, `void_reason`, `void_reason_note`).
- `Ticket`: kitchen-facing projection of an order, created by backend injection
  into the kitchen queue. Status (`incoming`, `preparing`, `ready`, `served`,
  `voided`). Records `injected_at` and `bump_ts` for cycle-time metrics.
- `Session`: one table occupancy window; opens on manual order start or prepaid
  webhook confirmation; primary close is explicit waiter close. Supports
  auto-extend (once per session, up to 30 min) when nearing end time within
  working hours and conflict boundaries. Overdue sessions beyond grace window
  are auto-closed by periodic Celery task.
- `CartSession`: ephemeral shared cart bound to a reservation. Status
  (`active`, `closed`). M2M participants (Users). Enforces
  one-active-per-reservation via partial unique constraint.
- `CartItem`: a line item within a CartSession. References `MenuItem`, tracks
  `quantity`, `guest_slot`, `guest_identity`, `comment`, `added_by`.
  Merged into a single row per session+menu_item via `get_or_create` with
  `F("quantity") + quantity` for concurrent safety.
- `GuestProfile`: per-cart-session guest identity mapping (`guest_identity` →
  `display_name`) for bill item attribution without requiring full User auth.
- `VoidReason`: seeded reason master with codes `mispick`, `guest_changed_mind`,
  `quality_issue`, `out_of_stock`.
- `Shift`: staff scheduling record for a restaurant. `employee` (User with
  role waiter/cook/admin), `date`, `start_time`, `end_time`, `notes`.
  Constrained: `end_time > start_time`. Indexed by `(restaurant, date)` and
  `(restaurant, employee, date)`.
- `Receipt`: immutable customer cabinet-history record, decoupled from
  operational Order/Session models. Snapshots `order_number`, `visited_at`,
  `currency`, `table_label`, `server_name`, `guests`, `tax`, `service_charge`,
  `tip`, `payment_method`, `payment_status`. Linked back to `Order` (nullable)
  and `Payment` (nullable). Created automatically on session close via
  `create_receipt_from_order`.
- `ReceiptItem`: line item within a Receipt. Snapshots `name`, `quantity`,
  `unit_price` from the menu item at time of creation so receipt stays correct
  if menu changes.
- `User`: `id`, `name`, `email`, role (`customer`, `cook`, `waiter`, `admin`).
  Role is a direct attribute on `User`. Uses `AbstractBaseUser +
  PermissionsMixin` with email as `USERNAME_FIELD` (no username column).
- `Payment`: provider transaction record. `order`, `provider`,
  `provider_transaction_id` (unique), `amount`, `currency`, `status`
  (`pending`, `authorized`, `paid`, `failed`, `refunded`, `cancelled`),
  `raw_payload` (JSON).
- `WebhookEvent`: immutable inbound webhook event record. `provider`,
  `event_id` (unique), `payload` (JSON), `received_at`, `processed_at`.
  Idempotency primitive for duplicate webhook deliveries.

### Role Access Matrix
Backend and frontend MUST implement this matrix consistently:

- `Cook`: kitchen kanban only; no floor plan, order creation, or financials.
  Can view own shifts.
- `Waiter`: floor plan, order creation, notification stream, table overlays;
  cannot approve voids, access financial reports, edit layout, or manage staff.
  Can view own shifts; cannot create/update/delete shifts for other staff.
- `Customer`: menu browsing, reservation creation, own-reservation access, and
  cart/session participation only; no staff operational endpoints, no kitchen,
  no financial/admin access, no shift visibility.
- `Admin`: full access, including financial reports, spatial editor, staff
  management (shifts CRUD, employee management), and menu control.

### Real-Time Delivery Contract

- One WebSocket connection per authenticated session MUST be maintained.
- Backend MUST maintain presence state for connected clients.
- Backend MUST broadcast role-targeted events.
- Event payloads MUST include `schema_version`.
- Existing event fields MUST NOT be removed from active versions; optional
  additive fields are allowed.
- At-least-once delivery per connected client is required.
- On reconnect, backend MUST replay events from the disconnection window for
  that session.

### Payment Contract

- Payment models (`Payment`, `WebhookEvent`) exist with idempotency primitives
  (unique `provider_transaction_id`, unique `event_id`).
- The full webhook-driven `unpaid -> paid` flow (signature validation, webhook
  processing, atomic paid+ticket injection) is specified (MVP US6, FR-029–FR-032)
  but NOT yet fully implemented. See Deferred TODOs.
- Current implementation uses a direct payment-marking flow: `pay_order_items`
  and `pay_session_bill` services mark `OrderItem.is_paid = True` and
  recompute `OrderPaymentStatus` — this is a simulated path for development.
- Payment and payment-derived event currency MUST come from
  `RestaurantSettings.currency` for the order's restaurant.
- Client or staff endpoints MUST NOT directly set paid status on settled orders.
- Payment records become immutable after successful confirmation.

### Void Contract

- Void reason code MUST be one of: `mispick`, `guest_changed_mind`,
  `quality_issue`, `out_of_stock`.
- Void request MUST include `is_wasted` to control inventory return behavior.
- Void execution MUST be all-or-nothing for: order-item state change to
  `voided`, session running-total decrement, corrected receipt queueing, and
  audit log creation.
- If receipt queueing fails, transaction MUST roll back.
- If WebSocket broadcast fails, data transaction MUST still commit.
- Kitchen void events MUST include backend-set high-priority cancellation flag.

### Cycle Time Metric Contract

- Ticket `injection_ts` and `bump_ts` MUST be recorded.
- Cycle time is `bump_ts - injection_ts`.
- Average Prep Time MUST be derived from raw cycle-time records at query time,
  not stored as a precomputed persistent column.
- Aggregations MUST support shift-level and day-level reporting views.

### Walk-In Contract

- Walk-in reservations are created by `create_walk_in_reservation` in
  `apps/orders/services/walk_in.py` when a waiter opens a table without a
  pre-existing booking.
- Walk-ins use `ReservationType.WALK_IN` and start immediately (`start_at =
  now`) with a default 2-hour end. End is clamped to the next existing booking
  to avoid overlap.
- Walk-in reservations have `customer = None` — the session opener (waiter) is
  tracked via `Session.opened_by`.
- Walk-in reservations are created with `status = ACTIVE` (no pending period).
- Idempotent: `ensure_visit_session` uses `get_or_create` per reservation so
  duplicate open-table calls do not create duplicate sessions.

### Receipt Contract

- Receipts are immutable customer cabinet-history records created at session
  close by `create_receipt_from_order` (`apps/receipts/services.py`).
- Line items snapshot `name`, `quantity`, `unit_price` from the menu at
  creation time to preserve fidelity after menu changes.
- Receipt creation is idempotent: uses `get_or_create` on the `order` FK.
- Orders with no attributable customer produce no receipt.
- `Receipt` is a standalone model, decoupled from operational `Order`/`Session`,
  so it can be managed by hand in Django admin for corrections or seeding.

### Cart Session Contract

- `CartSession` is the ephemeral shared ordering context per reservation.
- One active CartSession per reservation is enforced by partial unique
  constraint `one_active_per_reservation WHERE status = 'active'`.
- Participants are tracked via M2M to `User`. Non-participants are denied
  mutation access (`403 Forbidden`).
- Cart items are merged per `(session, menu_item)` — re-adding the same item
  increments quantity via `F("quantity") + quantity`. Concurrent adds are
  serialized via `select_for_update`.
- When an item becomes unavailable, it is pruned on checkout and
  `CartChangedError` is raised so the guest can review.
- Closed carts reject mutations with `409 Conflict` (error code
  `cart_session_closed`).
- Carts are not long-lived analytics records — the resulting Order/Receipt
  chain is the durable trail.

### Shift Management Contract

- `Shift` records are created/updated/deleted by `admin` role only.
- Staff users (`waiter`, `cook`) can view their own shifts; they cannot modify
  shifts.
- Shift overlap is not enforced at the DB level but `end_time > start_time` is
  enforced by `CheckConstraint`.
- Shifts are scoped to a `Restaurant` — one restaurant's staff schedule is
  isolated from others.
- Bulk operations: `copy_shifts` duplicates shifts from a source date to one or
  more target dates, optionally filtered by employee.

### Staff Notification Contract

- Staff notifications are broadcast to the `staff_<restaurant_id>` WebSocket
  group and persisted in Redis for history replay.
- Notification types: `CART_CREATED`, `CART_CHECKED_OUT`,
  `HALL_NEW_RESERVATION`, `ORDER_ITEM_STATUS_CHANGED`,
  `KITCHEN_TICKET_INJECTED`.
- History is stored per restaurant as a Redis list (bounded to 50 events,
  6-hour TTL). Payloads are sanitized/truncated before storage.
- Fallback to Django cache when Redis is unavailable.
- Notifications are informational (push-style); clients fetch full state via
  REST on receipt.

## Frontend Constitution

### I. Role Determines Interface Composition
Each role MUST mount only its own navigation, screens, and event handlers.
Unauthorized role components MUST NOT exist in the render tree.

Rationale: mounting unauthorized UI surfaces leaks complexity and risk.

### II. Floor Plan Is a Live Document
Waiter and admin floor-plan views MUST subscribe to live event streams and apply
backend patches immediately. Table status MUST be rendered from backend status
only, never inferred client-side.

Rationale: inferred state lags under concurrency and creates table confusion.

### III. Notifications Are a Stream
For waiter and admin sessions, notifications MUST be persistently mounted as a
stream with separate client and kitchen channels. Events MUST render
individually at arrival and tap-through MUST navigate directly to context.

Rationale: stream-first behavior preserves temporal clarity in busy service.

### IV. Status Colors Are Design Tokens
Order-item and table-status colors MUST be defined as semantic design tokens.
Components MUST NOT hardcode status-color values.

Rationale: semantic tokens keep state meaning consistent and maintainable.

### V. Modifier Modal Is a Critical Input Surface
Modifier modal MUST open in one tap, focus comment input on open, require guest
slot selection, and keep confirm disabled until required inputs are valid.

Rationale: modifier errors propagate directly into kitchen mistakes.

### VI. Offline Is an Error State
There is no offline write mode. On disconnection, UI MUST show a persistent
error state and block all write actions. After reconnect, clients MUST refresh
all open-session state before writes are re-enabled.

Rationale: degraded writes against stale state produce unrecoverable conflicts.

### VII. Spatial Editor Is a Separate Route Context
Spatial editor MUST be a dedicated route context, isolated from live monitoring
context. Live and edit canvases MUST NOT be mounted simultaneously.

Rationale: separation prevents accidental cross-mode state contamination.

### VIII. Destructive Actions Require Explicit Confirmation
Void, cancel reservation, and close table MUST present explicit confirmation
modals naming consequences. Void confirmation MUST require item name, reason
code, and `is_wasted` before enabling confirm. Close-table confirmation MUST
show total bill amount and served-item count before confirm.

Rationale: explicit confirmation reduces irreversible operational mistakes.

### IX. Floor Plan Performance Budget Is Mandatory
At full layout density, floor-plan updates MUST paint within 100ms of WebSocket
state delivery on a mid-range tablet. Table-icon rendering MUST avoid per-icon
network calls.

Rationale: delayed paint degrades service response during peak load.

### X. Theme Support Is First-Class
Customer and staff surfaces MUST support light/dark theme tokens. Staff dark
mode MUST be validated for high-ambient-light kitchen conditions and switch
instantly without flash.

Rationale: theme reliability is a usability and readability requirement.

## Backend Constitution

### I. Backend Owns State Transitions
Canonical state transitions MUST originate from backend processing. Clients MUST
not authoritatively transition canonical state.

Rationale: server authority prevents split-brain state.

### II. Event Catalog Is Explicit and Versioned
All live events MUST be in a catalog defining event name, schema,
`schema_version`, and audience. Schema changes MUST version forward.
Deprecations MUST span at least one release cycle.
Previous supported versions MUST continue to be emitted during migration until
clients have upgraded.

Rationale: catalog discipline protects client compatibility.

### III. Payment Webhook Is the Only Trusted Confirmation
`unpaid -> paid` transition MUST be exclusively webhook-driven after signature
validation.

Rationale: one trusted signal prevents paid-state abuse.

### IV. Void Transaction Is Atomic or No-Op
Void flow MUST execute in a transaction covering order-item state update,
session running-total decrement, void log write, corrected receipt queueing, and
kitchen/waiter void event publication intent, with explicit rollback on critical
downstream failures.

Rationale: void operations affect kitchen flow, receipts, and totals together.

### V. Kitchen Queue Uses Injection-Time Ordering
Kitchen queue priority MUST use injection timestamp only. Grouped cook views MAY
cluster by dish type but MUST preserve time ordering within each group.

Rationale: deterministic ordering is required for prep fairness.

### VI. Session Integrity Is Backend Responsibility
Session open/close rules MUST be explicit. Primary close MUST be
waiter-initiated (explicit close-table action). Two supporting automated
mechanisms exist as safety nets:
- **Auto-extend**: Open sessions nearing their end time are automatically
  extended by up to 30 minutes (once per session). Respects working-hours
  boundaries and upcoming reservation conflicts. Triggered by periodic Celery
  task (`orders.auto_extend_sessions`).
- **Grace-period close**: Sessions that remain open past their end time
  beyond the grace window (`SESSION_OVERDUE_AUTO_CLOSE_MINUTES`, default 20)
  are auto-closed by periodic Celery task (`orders.close_overdue_sessions`).
  Items must be served/voided before close; unresolvable sessions are skipped
  and retried on the next pass.
Close MUST persist immutable analytics snapshot (Receipt) and clear live
session state.

Rationale: explicit lifecycle boundaries preserve reporting accuracy; auto
mechanisms prevent table deadlock from forgotten sessions.

### VII. Authentication Is Role-Scoped at Token Level
Issued staff tokens MUST encode role identity. Backend MUST derive permissions
from canonical role mapping at request time. Role changes MUST invalidate active
tokens immediately.

Rationale: token-scoped identity blocks privilege spoofing and stale access.

### VIII. Floor Plan Layout Is Versioned and Immutable
Publishing layout MUST create immutable version records with stable table IDs.
Active sessions remain valid across versions. Layout updates MUST be delivered
through backend events.

Rationale: immutable versions avoid breaking active table references.

### IX. Financial Records Are Externally Read-Only
Public APIs MUST NOT create/update/delete financial records. Writes are limited
to internal flows: payment confirmation, void handling, and session close.
Receipt records (customer cabinet history) are created automatically at session
close as immutable snapshots of the finalized bill. Corrections are stored as
new records, never in-place overwrite.

Rationale: immutable financial writes preserve tamper-evident audits.

### X. Average Prep Time Is Query-Time Derived
Average Prep Time MUST be computed from raw cycle-time records at query time.
Metric queries MUST be indexed by restaurant and session timestamp. Backend read
paths supporting kitchen and floor-plan live views MUST include:

- `Ticket(restaurant, status, injected_at)` for FIFO `INCOMING` retrieval.
- `OrderItem(restaurant, status, menu_item)` for batch kitchen views.
- Partial index `Session(restaurant, table_id)` where `status = 'open'` for live
  floor-plan lookup.

Rationale: query-time derivation keeps corrections immediately accurate.

### XI. Async Task Infrastructure (Celery)
Background tasks (stale cart cleanup, session auto-extend, overdue session
close) MUST run via Celery with Redis as broker. Tasks are defined in
`apps/orders/tasks.py` and registered with `@shared_task`. Celery Beat
schedules periodic execution. Task failure MUST NOT block the request-response
cycle or WebSocket event delivery. Task discovery uses `app.autodiscover_tasks`.

Rationale: async cleanup prevents resource leak without coupling maintenance
to user-facing request paths.

### XII. Notification Store Is Redis-Backed
Staff notifications (cart created/checked-out, hall reservation events, kitchen
ticket injection, order-item status changes) MUST be persisted to Redis for
history replay. Storage uses a per-restaurant bounded list (default 50 events,
6-hour TTL) with LRU trimming. Payloads are sanitized/truncated before storage
to cap untrusted data volume. Consumers include a dedicated `staff_<id>`
WebSocket group. Fallback to Django cache is used when Redis is unavailable.

Rationale: persisted history lets newly connected staff clients reconstruct
recent floor activity without requiring full event replay from all streams.

### XIII. Walk-In Flow Creates Ephemeral Reservations
When a waiter opens a table without a pre-existing booking, the backend creates
a walk-in `Reservation` (type `WALK_IN`, status `ACTIVE`) with a default 2-hour
window. The reservation end is clamped to the next existing booking if one
exists. Walk-in reservations have no `customer` association — the session owner
(the waiter) is tracked via `Session.opened_by`.

Rationale: unifying walk-ins and pre-bookings under the `Reservation` entity
keeps the floor plan and billing models uniform.

### XIV. Receipt Snapshot Is Immutable and Decoupled
Receipts are created at session close (`close_visit_session` signals
`_finalize_session_orders_for_history` which calls `create_receipt_from_order`).
The Receipt model is decoupled from operational Order/Session models so it is
safe to manage by hand in Django admin. Line items snapshot `name`, `quantity`,
`unit_price` from the menu at creation time so the receipt stays correct if the
menu changes. Receipt creation is idempotent (uses `get_or_create` on Order FK).
Orders with no attributable customer (no guest reservation, no customer-created
order, no session opener) produce no receipt.

Rationale: decoupled snapshots preserve cabinet history fidelity independently
of live operational data evolution.

### XV. Cart Session Lifecycle Is Ephemeral
A CartSession is the shared ordering context for one reservation's guests. It
is created on first item addition or QR scan. One active CartSession per
reservation is enforced by a partial unique constraint
(`one_active_per_reservation`). The cart is closed when:
- Guest checks out (`checkout_cart_session` — items become an Order).
- Reservation is completed or cancelled (`close_reservation_carts`).
- Periodic Celery task closes stale carts (`close_stale_cart_sessions`).

Closed carts reject mutations with `409 Conflict`. Carts are not persisted as
analytics — the resulting Order and Receipt are the permanent records.

Rationale: ephemeral carts reduce cleanup complexity; the Order/Receipt chain
is the durable audit trail.

### XVI. Service Layer Organization
Services are organized by domain concern in a `services/` package split, not a
single monolithic `services.py`:
- `services/cart.py`: cart item CRUD, order creation, session management,
  payment marking, void operations.
- `services/sessions.py`: cart session lifecycle (create, ensure, stale close,
  auto-extend, overdue close).
- `services/walk_in.py`: walk-in reservation creation.

The `services/__init__.py` re-exports all public functions so callers import
from `apps.orders.services` as before. Splitting is internal-only.

Additional service modules outside the `services/` package:
- `apps/orders/billing.py`: checkout, session close, receipt finalization.
- `apps/receipts/services.py`: receipt snapshot creation from orders.

Rationale: concern-based splitting keeps each module under 700 lines while
preserving a stable public API surface.

- Mandatory workflow:
  `speckit-specify -> speckit-plan -> speckit-tasks -> speckit-implement`
  (or manual implementation from `tasks.md`).
- Plan artifacts MUST include constitution-gate evidence for all impacted
  principles.
- Spec artifacts MUST include role access effects, event contract/version
  impact, state-authority boundaries, and transaction semantics.
- Tasks artifacts MUST include verification for role enforcement, websocket
  replay/version handling, webhook signature checks, and atomic data behavior
  when relevant.
- Backend baseline MUST remain: Python 3.12, Django 5+, DRF, PostgreSQL, Redis,
  Channels, Celery (Redis broker), JWT auth, and Skinny Views / Fat Services /
  Selectors pattern.
- Required quality gates before merge: `ruff` (lint), `mypy` (type check),
  `bandit` (security), `pip-audit` (dependency vulns), tests (pytest).
  CI also enforces `drf-spectacular` schema drift detection and migration
  drift checks.

## Specification Process

### I. Cross-Repo Specification Principle

Feature specifications in `specs/<feature>/spec.md` are the shared source of
truth for BOTH frontend and backend development. Each spec MUST include:

- **Backend changes**: API endpoints, models, services, selectors, permissions,
  data contracts, events.
- **Frontend changes**: Pages, components, navigation, state management,
  user-facing flows, error/loading/empty states, accessibility notes.

Design artifacts (plan.md, tasks.md, data-model.md, contracts/README.md) are
also shared. Frontend and backend branches are developed simultaneously from the
same spec. Where a change affects only one surface, note the exclusion explicitly
to avoid ambiguity.

Rationale: parallel frontend/backend development requires a single spec both
teams can implement against. Separate specs diverge and create integration debt.

## Governance

- This constitution supersedes conflicting local conventions.
- Amendment process requires:
  - pull request discussion,
  - explicit approval,
  - updated Sync Impact Report in this file,
  - dependent template synchronization in `.specify/templates/*`.
- Versioning policy follows semantic versioning:
  - MAJOR: incompatible principle/governance changes.
  - MINOR: new principle or materially expanded mandatory guidance.
  - PATCH: wording-only clarification without normative change.
- Compliance reviews are mandatory at planning, task generation, code review,
  and CI.

**Version**: 2.2.0 | **Ratified**: 2026-05-06 | **Last Amended**: 2026-07-27
