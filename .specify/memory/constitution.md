<!--
Sync Impact Report
- Version change: 2.0.0 -> 3.0.0
- Modified principles:
  - I. Right Role, Right Moment, Zero Ambiguity -> I. Backend Owns All State
    Transitions
  - II. Canonical Shared Data Contracts -> II. WebSocket Events Deliver All
    Live State
  - III. Backend-Enforced Role Access Matrix -> III. Payment Webhook Is the
    Trusted Confirmation Signal
  - IV. WebSocket-Only Live State and Event Versioning -> IV. Void Execution Is
    Atomic at the Data Layer
  - V. Transactional State Integrity -> V. Kitchen Queue Ordering Uses
    Injection Time
- Added sections:
  - VI. Session Integrity Is Backend-Managed
  - VII. Staff Authentication Is Role-Scoped at Token Level
  - VIII. Floor Plan Layout Is Immutable and Versioned
  - IX. Financial Data Is API Read-Only
  - X. Average Prep Time Is Computed from Raw Cycle Time Records
- Removed sections:
  - None
- Templates requiring updates:
  - ✅ .specify/templates/plan-template.md
  - ✅ .specify/templates/spec-template.md
  - ✅ .specify/templates/tasks-template.md
  - ⚠ pending: .specify/templates/commands/*.md (directory not present in this
    repository; no files to validate)
- Deferred TODOs:
  - None
-->

# TableMate Platform Constitution

## Core Principles

### I. Backend Owns All State Transitions
Canonical entities MUST transition state only through backend-controlled
operations. Clients MUST NOT optimistically transition canonical state and sync
later. Every state change (table status, order item lifecycle, payment status,
session open/close) MUST be initiated by backend request handling and confirmed
by backend event broadcast. The event broadcast is the authoritative state
announcement, not a non-authoritative notification.

Rationale: backend-owned transitions prevent divergent client truth and remove
race-induced ambiguity.

### II. WebSocket Events Deliver All Live State
Live state delivery MUST use WebSocket only. REST endpoints MUST handle
creation and mutation and MUST NOT be used for polling live updates. The
backend MUST maintain a typed event catalog where every event defines name,
schema, audience, and `schema_version`. Event schema changes MUST be versioned,
event removals MUST include a deprecation period of at least one release cycle,
and existing event fields MUST NOT be removed from active versions.

Event delivery MUST provide at-least-once delivery per connected client.
On reconnect, the backend MUST replay events that occurred during the
disconnection window for that session.

Rationale: role-timed operations require deterministic, replay-safe live-state
delivery.

### III. Payment Webhook Is the Trusted Confirmation Signal
Customer-originated payment confirmation MUST be accepted only through the
payment provider webhook endpoint after signature validation. Orders MUST
transition from `unpaid` to `paid` only through this webhook path. No client
request, staff action, or internal shortcut endpoint may perform this
transition directly.

On successful validation, the backend MUST atomically mark the order paid,
inject the ticket into the kitchen queue, and broadcast relevant events to
waiter and kitchen channels.

Rationale: a single verified signal prevents payment-state manipulation.

### IV. Void Execution Is Atomic at the Data Layer
Void execution MUST be implemented as a database transaction with explicit audit
data. The transaction scope MUST include: `OrderItem` status update to
`voided`, session running-total decrement, void log entry with reason code and
`is_wasted`, and corrected receipt queueing. If receipt queueing fails, the
transaction MUST roll back.

WebSocket broadcast failures MUST NOT roll back committed data updates; data
integrity has higher priority than live event transport. Kitchen void events
MUST include a backend-set priority flag for cancellation audio behavior.

Rationale: the system must guarantee correct financial/kitchen data even during
transport outages.

### V. Kitchen Queue Ordering Uses Injection Time
Kitchen queue ordering MUST be based on ticket injection timestamp only. Table
number, waiter identity, and order size MUST NOT affect queue position. Batch
views MAY group by dish type but MUST preserve injection-time ordering within
each group.

Rationale: strict timestamp ordering preserves fairness and predictable prep
flow.

### VI. Session Integrity Is Backend-Managed
Session lifecycle ownership belongs to the backend. Sessions MUST open when
manual ordering starts or prepaid webhook confirmation arrives. Sessions MUST
close only when waiter-triggered close-table action is received. Backend
timeouts or inactivity heuristics MUST NOT auto-close sessions.

At session close, backend MUST create a permanent analytics snapshot that
includes revenue, cycle times, void count, and item count, then clear live
session state.

Rationale: human-controlled closure and immutable snapshots protect operational
traceability.

### VII. Staff Authentication Is Role-Scoped at Token Level
Staff tokens MUST encode role identity and backend authorization MUST derive
permissions from canonical role mapping at request time. The backend MUST NOT
accept role identity from request body or client-supplied headers.

If an admin changes a staff role, active tokens for that staff account MUST be
invalidated immediately and re-authentication MUST be required.

Rationale: token-scoped identity prevents privilege spoofing and stale grants.

### VIII. Floor Plan Layout Is Immutable and Versioned
Each published layout MUST create a new immutable version and set it as active
for the restaurant while preserving prior versions. Table IDs MUST remain stable
across layout versions. If sessions are active during publication, backend MUST
broadcast layout-updated events containing the new version payload.

After initial load, clients MUST apply floor-plan changes only from backend
broadcast events and MUST NOT independently refetch layout as an update path.

Rationale: immutable versions preserve referential safety for active sessions.

### IX. Financial Data Is API Read-Only
External APIs MUST NOT create, update, or delete financial records. Financial
records MUST be written only by internal backend flows (payment confirmation,
void transaction, and session-close snapshot). Financial APIs may expose read
aggregation and filtering only.

Rationale: immutable financial writes preserve auditability and prevent
tampering.

### X. Average Prep Time Is Computed from Raw Cycle Time Records
Average Prep Time MUST be computed at query time from raw cycle-time records and
MUST NOT be stored as a precomputed persisted metric column. Historical cycle
time corrections MUST be reflected immediately in query results without separate
recompute jobs. Query paths for this metric MUST be indexed by restaurant and
session timestamps.

Rationale: raw-record computation keeps analytics correct under historical
corrections.

## Operational Constraints

### Foundation Scope
TableMate is a real-time, multi-role restaurant operations platform shared by
frontend and backend. The platform surfaces are Customer, Waiter, Cook, and
Admin. Latency and inconsistency are functional defects, not UX-only concerns.

### Canonical Shared Data Contracts
Frontend and backend MUST treat the following contracts as source of truth and
MUST NOT create role-specific local variants:
- `Restaurant`: `id`, `name`, working hours, active floor-plan reference, and
  QR-code mappings to table IDs.
- `Table`: `id`, sector assignment, capacity, and status
  (`free`, `reserved`, `occupied`). Status is backend-computed and backend-
  pushed only.
- `Order`: `id`, table reference, session reference, origin
  (`waiter_manual` or `customer_prepaid`), payment status
  (`unpaid`, `paid`, `settled`), and `OrderItems`.
- `OrderItem`: `id`, menu item reference, quantity, modifier text, guest slot
  index, and lifecycle status
  (`pending`, `in_progress`, `ready`, `voided`, `completed`).
- `Ticket`: kitchen projection of an order, created when backend injects order
  into kitchen queue.
- `Session`: active occupancy window for one table; opens on waiter manual
  order start or prepaid webhook, closes on explicit close-table action.
- `Staff`: `id`, `name`, `email`, assigned role (`cook`, `waiter`, `manager`,
  `owner`), shift status (`online`, `offline`).

### Role Access Matrix
Backend MUST enforce this matrix on every request:
- `Cook`: kitchen kanban only; no floor plan, order creation, or financials.
- `Waiter`: floor plan, order creation, notification stream, and table detail
  overlays; cannot approve voids, view financial reports, or edit layout.
- `Manager`: inherits waiter permissions and may approve voids and discounts;
  cannot access financial reports, spatial editor, or staff management.
- `Owner`: full access including financial reports, spatial editor, staff
  management, and menu control.

### Real-Time Architecture Constraints
- Live state transport is WebSocket only; REST handles create/mutate flows.
- One WebSocket connection per authenticated session MUST be maintained.
- Backend MUST track presence state for connected clients.
- Backend MUST broadcast targeted events by role and context.
- Events MUST be typed and versioned; unknown versions are ignored client-side.
- Existing event fields MUST NOT be removed from active schema versions.

### Platform and Architecture Baseline
- Supported customer payment methods are Apple Pay, Google Pay, and card.
- Backend stack is mandatory: Python 3.12, Django 5+, DRF, PostgreSQL, Redis,
  Channels, and JWT auth.
- Backend architecture pattern is mandatory: Skinny Views, Fat Services,
  Selectors.

## Development Workflow

- Mandatory flow: `speckit-specify -> speckit-plan -> speckit-tasks ->
  speckit-implement` (or manual implementation from `tasks.md`).
- Spec artifacts MUST include: role access matrix impacts, event catalog/schema
  changes, replay semantics, authoritative state transitions, and immutable data
  boundaries where applicable.
- Plan artifacts MUST include a Constitution Check gate per principle and
  document any justified exception explicitly.
- Tasks MUST include verification for:
  - role-based authorization,
  - event versioning and replay behavior,
  - webhook signature validation,
  - atomic and rollback behavior for payment/void/session flows,
  - immutable/reporting constraints.
- CI gates MUST pass before merge: `flake8`, `bandit`, `safety`, and tests.

## Governance

- This constitution supersedes ad-hoc local conventions.
- Amendments require pull request discussion, explicit approval, and an updated
  Sync Impact Report in this file.
- Semantic versioning policy:
  - MAJOR: principle redefinition/removal or incompatible governance changes.
  - MINOR: new principle or materially expanded mandatory guidance.
  - PATCH: clarification-only or editorial updates with no normative change.
- Compliance reviews are mandatory during planning, task generation, code
  review, and CI validation.

**Version**: 3.0.0 | **Ratified**: 2026-05-06 | **Last Amended**: 2026-05-11
