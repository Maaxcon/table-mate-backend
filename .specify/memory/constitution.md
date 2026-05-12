<!--
Sync Impact Report
- Version change: 1.0.0 -> 1.1.0
- Modified principles:
  - None
- Modified sections:
  - Foundation Contracts / Canonical Entity Definitions (added `RestaurantSettings`, added top-level `Menu`, clarified `Restaurant` scope)
  - Foundation Contracts / Payment Contract (currency source anchored to `RestaurantSettings.currency`)
- Added sections:
  - None
- Removed sections:
  - None
- Templates requiring updates:
  - ✅ .specify/templates/plan-template.md (no changes required)
  - ✅ .specify/templates/spec-template.md
  - ✅ .specify/templates/tasks-template.md
  - ⚠ pending: .specify/templates/commands/*.md (directory not present in this repository)
- Deferred TODOs:
  - None
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
  `timezone`, `currency`, `locale`, `working_hours`, `default_tax_rate`.
- `Table`: `id`, sector, capacity, and status (`free`, `reserved`, `occupied`).
  Status is backend-computed and backend-pushed only.
- `Menu`: top-level menu container for a restaurant (for example breakfast,
  lunch, dinner) with `id`, restaurant reference, `name`, service window
  metadata, active flag, and menu item/category associations.
- `Order`: `id`, table reference, session reference, origin
  (`waiter_manual`, `customer_prepaid`), payment status
  (`unpaid`, `paid`, `settled`), and `OrderItem[]`.
- `OrderItem`: `id`, menu item reference, quantity, modifier text, guest slot
  index, lifecycle status (`pending`, `in_progress`, `ready`, `voided`,
  `completed`).
- `Ticket`: kitchen-facing projection of an order, created by backend injection
  into the kitchen queue.
- `Session`: one table occupancy window; opens on manual order start or prepaid
  webhook confirmation; closes only by explicit close-table action.
- `Staff`: `id`, `name`, `email`, role (`cook`, `waiter`, `manager`, `admin`),
  shift status (`online`, `offline`).

### Role Access Matrix
Backend and frontend MUST implement this matrix consistently:

- `Cook`: kitchen kanban only; no floor plan, order creation, or financials.
- `Waiter`: floor plan, order creation, notification stream, table overlays;
  cannot approve voids, access financial reports, edit layout, or manage staff.
- `Manager`: inherits waiter permissions and may approve voids and discounts;
  cannot access financial reports, spatial editor, or staff management.
- `Admin`: full access, including financial reports, spatial editor, staff
  management, and menu control.

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

- Customer-originated orders transition from `unpaid` to `paid` only through a
  validated payment-provider webhook.
- The webhook signature MUST be validated before state transition.
- Payment and payment-derived event currency (including
  `PAYMENT_CONFIRMED.currency`) MUST come from `RestaurantSettings.currency` for
  the order's restaurant.
- Successful confirmation MUST atomically: mark order paid, inject ticket into
  kitchen queue, and broadcast role-relevant events.
- Client or staff endpoints MUST NOT directly set paid status.
- There is no "call waiter" fallback for customer-originated unpaid orders.
- Supported payment methods are Apple Pay, Google Pay, and card.

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
Session open/close rules MUST be explicit and human-controlled for closure.
Automatic timeout closure is forbidden. Session close MUST be waiter-initiated.
Close MUST persist immutable analytics snapshot and clear live session state.

Rationale: explicit lifecycle boundaries preserve reporting accuracy.

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

Rationale: immutable financial writes preserve tamper-evident audits.

### X. Average Prep Time Is Query-Time Derived
Average Prep Time MUST be computed from raw cycle-time records at query time.
Metric queries MUST be indexed by restaurant and session timestamp.

Rationale: query-time derivation keeps corrections immediately accurate.

## Development Workflow

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
  Channels, JWT auth, and Skinny Views / Fat Services / Selectors.
- Required quality gates before merge: `flake8`, `bandit`, `safety`, tests.

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

**Version**: 1.1.0 | **Ratified**: 2026-05-06 | **Last Amended**: 2026-05-12
