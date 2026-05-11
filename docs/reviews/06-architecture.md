# TableMate — Architecture Review

Reviewer perspective: Django 5 + DRF + Channels (Daphne) backend, Postgres. Apps scaffolded: `authentication`, `editor`, `menu`, `orders`, `reservations`, `restaurants`. Critique is against the spec `docs/architecture-and-workflows.md` (Parts 1–4 + AC for Developers 1/2/3).

Each axis below: **(a) what's missing**, **(b) concrete recommendation**, **(c) priority H/M/L**.

---

## 1. Data Model Completeness

**(a) Missing.** AC1 of Feature 0 only names Restaurant, Table, Session, Order, OrderItem, Ticket, Staff. Walking the workflows surfaces entities the spec demands but never models:

- **Reservation** — Phase 2 client booking, "Reserved (Patterned/Gray)" table state, modify/cancel lifecycle, conflict-checking against working hours. Cannot exist as a denormalized field on `Table`.
- **MenuCategory / MenuItem / Variant / Modifier / ModifierGroup** — Waiter Phase 4 ("tap menu item, Modifier Modal appears"), Admin Phase 4 "Digital Pantry", Client menu browsing. Spec assumes these but Feature 0 doesn't list them.
- **Allergen** (M2M with MenuItem) — referenced indirectly by "conflicting modifiers" check in Waiter Phase 3; legally important in EU venues.
- **InventoryItem / StockToggle** — "Emergency Stock Toggles" (Admin Phase 4.3) need a real entity; tying out-of-stock to `MenuItem.is_active` collapses two distinct lifecycles.
- **Payment / PaymentAttempt / Refund / Chargeback** — Feature 4 talks about webhooks and "Settled" but there is no model. An `Order.status='Paid'` field is not enough for partial captures, refunds, disputes, idempotency replay.
- **Tax / TaxRate / OrderItemTaxLine** — VAT is essential for EU venues, missing entirely.
- **Discount / Comp / Promotion** — Admin will need discounting; not mentioned, will be added in the worst way (ad-hoc) without an entity.
- **VoidEvent / VoidReasonCode** — Feature 7 references reason codes and `is_wasted`; this is an immutable audit record, not a flag on OrderItem.
- **WasteLog** — separate from VoidEvent because waste can occur without a sale (spoilage); admin analytics will need it.
- **Shift / ShiftRecord / TimeClockEntry** — "Staff Load" KPI (Admin Phase 1.1) and "Shift Reporting" (Admin Phase 5.3) require clock-in/out.
- **TipDistribution** — implied by Shift Reporting; ignored by spec.
- **LayoutVersion / FloorSection / TableLayoutPlacement** — Feature 10 AC2 says "immutable layout JSON version… preserving historical versions". This must be a versioned entity, not a JSONB blob on `Restaurant`.
- **MergedTableGroup** — Real restaurants merge T-04+T-05 for a party of 8; spec ignores it. Without it, the Session ↔ Table cardinality breaks.
- **Notification / NotificationDelivery** — Feature 8 (sidebar streams) and Phase 2 alerts need persistence so they can be replayed (Feature 2 AC3).
- **AuditLogEntry** — Feature 1 AC3 (role change forces re-auth) and Feature 11 AC3 (no external write on financials) imply an audit trail; nothing models it.
- **PrinterRoute / KitchenStation** — multi-station kitchens route Bartender vs. Grill vs. Cold-prep tickets; a single global "INCOMING" column is unrealistic.
- **Receipt** — Phase 4 Client History references "itemized electronic receipts"; should be an immutable, signed snapshot, not re-rendered from live Order rows.
- **Review / Rating** — Scenario B explicitly says "only booking and reviews are available remotely"; no model.
- **Guest / GuestSeat** — Waiter Phase 4.1 creates "Guest Slots" and prepaid orders show items "pre-organized by guest seat"; this needs a row, not an integer column on OrderItem.
- **Device / KdsTerminal** — KDS bumps and audio chimes are tied to a physical terminal; needed for printer-fallback and observability.

**(b) Recommendation.** Add the entities above (sketches in the final section). Treat Feature 0 AC1 as a starting subset and explicitly extend it in a follow-up ADR.

**(c) Priority: H.**

---

## 2. State Machines Made Explicit

**(a) Missing.** Prose implies states ("Free / Reserved / Occupied", "Pending / In Progress / Ready", "Paid", "Voided", "Completed", "Closed") but no FSM with allowed transitions, guards, or actors. ENUMs (AC2) without transition rules let any handler write any state.

**(b) Recommendation.** Codify FSMs in `apps/<domain>/state.py` with explicit allowed transitions and a single transition function that emits the matching WS event.

```
Table:
  FREE → RESERVED (host/system on Reservation.confirm)
  FREE → OCCUPIED (waiter "Seat guests" / QR scan)
  RESERVED → OCCUPIED (host "Check-in")
  RESERVED → FREE (reservation cancel / no-show timeout)
  OCCUPIED → DIRTY (waiter "Close Table" after payment)
  DIRTY → FREE (busser/auto-timer)
  OCCUPIED → MERGED (admin merge action) — child relation
  any → OUT_OF_SERVICE (admin)

Session:
  OPEN → AWAITING_PAYMENT (waiter "Request bill")
  AWAITING_PAYMENT → SETTLED (payment captured)
  AWAITING_PAYMENT → OPEN (split-bill cancel)
  SETTLED → CLOSED (waiter "Close Table" → snapshot)
  OPEN → CLOSED_VOID (admin abandon — rare)

Order:
  DRAFT → SUBMITTED (waiter "Send to Kitchen" / client pay)
  SUBMITTED → FIRED (Approve & Fire or auto)
  FIRED → PARTIALLY_READY → READY → SERVED
  any → VOIDED (admin Void on whole order)

OrderItem:
  PENDING (gray) → IN_PROGRESS (yellow, on cook claim)
  IN_PROGRESS → READY (green, on atomic tap)
  READY → SERVED (waiter pickup)
  any pre-SERVED → VOIDED (admin) with VoidEvent
  PENDING → CANCELLED (before fire; refundable cleanly)

Ticket:
  QUEUED → ACTIVE (cook claim) — claim is exclusive
  ACTIVE → BUMPED (all items READY + BUMP tap)
  any → RECALLED (waiter recall after bump — needed!)
  any → VOIDED

Payment:
  REQUIRES_ACTION → AUTHORIZED → CAPTURED → SETTLED
  AUTHORIZED → CANCELLED (timeout)
  CAPTURED → REFUNDED_PARTIAL → REFUNDED_FULL
  CAPTURED → DISPUTED → CHARGEBACK
  any failed → FAILED (with retry policy)

Reservation:
  PENDING → CONFIRMED (auto or host)
  CONFIRMED → CHECKED_IN (host)
  CONFIRMED → CANCELLED_BY_GUEST / CANCELLED_BY_VENUE / NO_SHOW
  CHECKED_IN → SEATED (links to Session.OPEN)
```

Each transition records `actor_id`, `at`, `reason?`, into `AuditLogEntry`.

**(c) Priority: H.**

---

## 3. WebSocket Event Catalog

**(a) Missing.** Feature 2 AC2 says events are role-scoped but no event names, payload shapes, or idempotency contract are defined. AC3 promises at-least-once but the catalog of *what* is replayed is undefined.

**(b) Recommendation.** Define an explicit event envelope and channel taxonomy. Envelope:

```jsonc
{
  "id": "evt_01HZ...",        // ULID, monotonic per restaurant
  "type": "order.item.status_changed",
  "version": 1,
  "restaurant_id": "rst_...",
  "occurred_at": "2026-05-11T18:00:00Z",
  "actor": { "type": "staff", "id": "stf_..." },
  "idempotency_key": "kds:tap:item:oi_123:to:READY",
  "data": { ... }
}
```

Channels (Channels groups):
- `rst:<rid>:floor` — Waiter+Admin
- `rst:<rid>:kds:<station>` — Cook+Admin
- `rst:<rid>:admin` — Admin only
- `rst:<rid>:table:<tid>` — Table-scoped (Waiter assigned + diners in session)
- `rst:<rid>:session:<sid>` — Diners only
- `user:<uid>` — direct (e.g., notifications)

Catalog (non-exhaustive, mapped to spec):

| Event type | Trigger | Channels | Payload keys | Idempotency key |
|---|---|---|---|---|
| `table.state_changed` | Table FSM | floor, admin | `table_id, from, to, session_id?` | `tbl:<id>:rev:<n>` |
| `table.session.opened` | Session OPEN | floor, table | `session_id, table_id, opened_by` | `sess:<id>:open` |
| `table.session.closed` | Session CLOSED | floor, admin | `session_id, total, duration_s` | `sess:<id>:close` |
| `reservation.created` | Reservation create | floor, admin | `reservation_id, table_id, window` | `rsv:<id>:v1` |
| `reservation.updated` | reschedule/cancel | floor, admin, user | `reservation_id, status, …` | `rsv:<id>:v<n>` |
| `order.created` | Submit/Pay | table, floor, admin | `order_id, table_id, source` | `ord:<id>:create` |
| `order.fired` | Approve & Fire | kds, table, admin | `order_id, ticket_id` | `ord:<id>:fire` |
| `order.item.status_changed` | KDS tap | kds, table, floor | `order_item_id, from, to` | `oi:<id>:to:<state>` |
| `order.item.voided` | Admin void | kds (priority), table, admin | `order_item_id, reason, is_wasted` | `oi:<id>:void` |
| `kitchen.ticket.claimed` | Cook claim | kds, floor | `ticket_id, cook_id` | `tkt:<id>:claim:<cook>` |
| `kitchen.ticket.bumped` | BUMP | kds, table, floor, admin | `ticket_id, cycle_time_s` | `tkt:<id>:bump` |
| `kitchen.batch.ready` | Batch | kds, table, floor | `item_signature, ticket_ids[]` | `batch:<sig>:<ts>` |
| `payment.succeeded` | Stripe webhook | table, kds, admin | `payment_id, order_id, amount, currency` | `pay:<id>:succeeded` |
| `payment.refunded` | Refund | admin, user | `payment_id, amount, reason` | `pay:<id>:refund:<n>` |
| `inventory.item.eighty_sixed` | Admin toggle | floor, table, client | `menu_item_id, available` | `menu:<id>:avail:<bool>:<ts>` |
| `floor.layout.published` | Editor publish | floor, admin | `layout_version_id` | `layout:<id>:publish` |
| `notification.created` | Any actionable | user, role | `notification_id, target_kind, target_id` | `ntf:<id>` |
| `presence.staff_online` | WS connect | admin | `staff_id` | `presence:<sid>:<ts>` |

**(c) Priority: H.**

---

## 4. Concurrency & Contention

**(a) Missing.** Spec has zero discussion of:
- Two cooks tapping the same ticket → "Claim" race.
- Admin publishing a layout while waiter is editing a seating.
- Stripe webhook duplicates (`payment_intent.succeeded` fires multiple times in retries).
- Two waiters simultaneously tapping "Close Table".
- Atomic Void (Feature 7 AC2) mentions "atomic DB transaction" but says nothing about cross-service ordering (DB commit vs WS broadcast vs printer push).

**(b) Recommendation.**

- **Optimistic concurrency**: add `version BIGINT` to Table, Session, Order, OrderItem, Ticket, Layout. Reject writes with `If-Match` mismatch (HTTP 409). Increment on every transition.
- **Pessimistic where short**: `SELECT … FOR UPDATE SKIP LOCKED` on Ticket claim — first cook wins, others get a 409 immediately.
- **Idempotency table**: `idempotency_keys(key TEXT PK, request_hash, response_json, created_at, ttl)`. Required header on all `POST/PATCH/DELETE` and for webhook handlers. Stripe webhook reuses `event.id` as the key.
- **Outbox pattern** (see axis 5) so DB-commit and WS-broadcast cannot diverge.
- **Saga / Transactional event log** for the Stripe→Kitchen handshake (Feature 4 AC3): `order.paid` write + outbox row in one tx; Channels consumer reads outbox.
- **Distributed lock** (Redis SETNX with TTL) for Layout publish to serialize editors; combined with `LayoutVersion.parent_version_id` for CAS.

**(c) Priority: H.**

---

## 5. At-Least-Once Delivery & Replay

**(a) Missing.** Feature 2 AC3 says reconnect replay must guarantee at-least-once but no mechanism is specified. There is also no defined boundary between "events to replay" and "state to refetch". With Channels alone, events not delivered while disconnected are lost.

**(b) Recommendation.**

- **Event log table** `event_log(id ULID PK, restaurant_id, type, payload jsonb, occurred_at)` partitioned by month. ULID gives a monotonic cursor.
- **Per-connection cursor**: client sends `last_event_id` on (re)connect; server streams `event_log.where(id > cursor and channel ∈ allowed)` then catches up to live. Cursor stored client-side (localStorage), not server-side.
- **Outbox pattern**: domain writes append to `outbox`; a single worker copies outbox → `event_log` + Channels group_send. This guarantees DB and WS converge.
- **Bounded replay window**: 24 h or 5 000 events, whichever smaller; beyond that, force a full snapshot refresh (`/sync/floor`, `/sync/kds`).
- **De-dup on client**: events carry `id`; client maintains a small LRU of seen IDs to handle the at-least-once → at-most-once-displayed conversion.
- **Payment interaction**: Stripe webhooks write to outbox with `idempotency_key = event.id`; replay never re-fires Stripe-side actions, only re-broadcasts the state event.

**(c) Priority: H.**

---

## 6. Payment Edge Cases

**(a) Missing.** Feature 4 AC1–3 covers happy path only. Real situations to handle:

- Webhook arrives *after* the diner closed the app / table was closed.
- Partial capture (auth $50, capture $42 after kitchen voids one item).
- Refund/void after Bump (kitchen already cooked it).
- Chargeback days later → reverse revenue, leave audit.
- Apple Pay sheet times out mid-network → user retries → duplicate `payment_intent`.
- 3DS challenge requires `requires_action`; spec assumes synchronous success.
- Tip added after capture (Stripe `update`).
- Refunds may not reach Stripe (network) — needs reconciliation job.

**(b) Recommendation.**

- Persist a full `Payment` table with FSM (axis 2). One Order may have many Payments (split bill, retries).
- All Stripe calls take `Idempotency-Key = "pay:<order_id>:<attempt_uuid>"`.
- Webhook handler is the *sole* source of truth for `Payment.status`; client-side success is advisory only.
- On `payment_intent.succeeded` after `Order.status=CLOSED_VOID`: log a `PaymentOrphaned` audit row + auto-refund job (configurable).
- Daily reconciliation job: pull Stripe `balance_transactions`, diff vs local `Payment` table, alert on drift.
- Map Stripe webhook events: `requires_action`, `processing`, `succeeded`, `payment_failed`, `amount_capturable_updated`, `charge.refunded`, `charge.dispute.created`.
- Disputes: write-only ledger; never mutate prior `Payment` row.

**(c) Priority: H.**

---

## 7. Multi-Tenancy

**(a) Missing.** Spec assumes a single restaurant tenant per request but never specifies how multi-restaurant isolation is enforced. With JWT carrying only `role`, a Cook from Restaurant A could in principle query Restaurant B's order. Owners running multiple venues are mentioned implicitly ("multi-venue" in Reservations time axis) but not modelled.

**(b) Recommendation.**

- Every entity (except global lookup tables) carries `restaurant_id` NOT NULL with FK + composite index on (restaurant_id, …).
- JWT payload: `{ sub, role, restaurant_id, allowed_restaurant_ids[] }`. Owners may belong to many.
- Enforcement at **two layers**:
  1. Default DRF queryset filter via a `TenantScopedManager` keyed off `request.tenant`.
  2. Postgres Row-Level Security as a defence-in-depth net: `SET LOCAL app.restaurant_id = …` per request; policies on every table.
- Channels groups always prefixed `rst:<rid>:…` (axis 3); subscription validated against JWT's `allowed_restaurant_ids` on connect.
- Cross-restaurant analytics (Owner dashboard) goes through a separate aggregate read-model service.
- Test: add a chaos test that drops `request.tenant` and verifies queries return zero rows.

**(c) Priority: H.**

---

## 8. RBAC Depth

**(a) Missing.** Feature 1 lists Cook/Waiter/Manager/Owner. Real venues need finer separation:

- **Owner** (multi-venue, financial, payouts) vs **Manager** (single venue, ops/staff/menu).
- **Host/Greeter** — manages floor seating, no order writes.
- **Expediter** — kitchen pass, can bump tickets but not claim cook stations.
- **Bartender** — separate ticket route (Drink station), can mark bar items only.
- **Trainee** — read-only or sandbox mode.
- **Busser** — table state Dirty→Free only.

Also missing: scope qualifier ("can void < €20 without manager approval"), permission delegation, time-bound elevation ("manager override PIN").

**(b) Recommendation.** Replace role enum with a permission matrix:

```
Role —< RolePermission >— Permission
Staff —< StaffRole (with restaurant_id scope and validity window) >— Role
```

Permission codes like `order.item.void`, `order.item.void.over_limit`, `layout.publish`, `payment.refund`, `menu.eighty_six`. Enforce with a DRF permission class and a Channels middleware that resolves `staff_id → permissions` once per connection.

Add a **Manager Override** flow: PIN-gated elevation creating a short-lived JWT (5 min) with extra scopes, fully audited.

**(c) Priority: H.**

---

## 9. Offline-First / Network Resiliency

**(a) Missing.** Feature 12 AC2 hard-disables writes during disconnect. For a busy kitchen this kills throughput when wifi blips for 10 s. AC1 forces a banner — fine — but locking out *all* writes is brittle.

**(b) Recommendation.**

- Distinguish **safe-offline writes** (KDS tap "Item Ready", BUMP) from **unsafe** (Close Table, Pay, Publish Layout). Safe ones go into a local write-ahead queue with optimistic UI; sync replays on reconnect with idempotency keys.
- Use **Service Worker + IndexedDB** on the KDS web app; queue events with the same envelope schema (axis 3) and replay on reconnect.
- Reconcile conflicts via server-side FSM rejection (item already SERVED) and surface a non-blocking toast.
- For absolutely critical writes (Pay, Close Table), keep the hard-disable + banner.
- KDS terminals should be able to print to a local ESC/POS printer over LAN as last-resort fallback if the WS server is unreachable (printer route configured per `KitchenStation`).

**(c) Priority: M.**

---

## 10. Time & Timezone

**(a) Missing.** Spec talks about "19:00 TODAY" and "12 OCT 2024" with zero timezone discussion. Reservation windows cross DST. Owners with multi-venue chains span timezones. Shift Reporting needs "business day" semantics (a shift starting 22:00 closes 06:00 next "day" — for accounting it's the prior day).

**(b) Recommendation.**

- Store all timestamps as `TIMESTAMPTZ` in UTC.
- `Restaurant.timezone` (IANA, e.g., `Europe/Zurich`) is canonical.
- Render in venue tz on server (Owner dashboard) or pass venue tz to client.
- Define a `business_date` function that maps a timestamp to the venue's accounting day (e.g., cutoff at 04:00 local) and use it for all daily KPIs.
- Reservations carry `(start_at_utc, end_at_utc, restaurant_tz)`; reschedule logic uses the tz to recompute valid slots.
- All client UIs render via `Intl.DateTimeFormat` with venue tz, never browser tz.

**(c) Priority: M.**

---

## 11. Money Handling

**(a) Missing.** Spec writes "€142.00" but never defines how money is stored. No discussion of VAT (mandatory in EU), tax-inclusive vs exclusive pricing, multi-currency for tourist venues, rounding.

**(b) Recommendation.**

- Money as **integer minor units** (`amount_cents INTEGER`, `currency CHAR(3) ISO-4217`). Never float.
- Server-side validation: every `MoneyAmount` carries both fields; mismatched currency in a single order → reject.
- `Tax` and `TaxRate` entities with effective-from/to; `OrderItemTaxLine` snapshots rate at fire-time (so historical receipts don't change when rates do).
- Pricing model: `MenuItem.price_cents` + `tax_inclusive BOOLEAN` per restaurant; compute `gross/net/tax` deterministically.
- Multi-currency: each Order is single-currency; cross-currency conversion only at Owner dashboard, with a stored daily FX snapshot.
- Rounding: bankers' rounding for tax line items; document and unit-test.
- Tip handling: separate line, not folded into item totals; tipping after capture uses Stripe `tip_amount` if available.

**(c) Priority: H.**

---

## 12. Observability

**(a) Missing.** Spec is silent on logging/metrics/tracing. Feature 9 AC1 makes a hard claim ("repaint < 100 ms") and Feature 5 AC1 ("Modifier Modal < 100 ms") with no SLO definition or measurement plan. Feature 4 AC3 stitches webhook → DB → kitchen WS — a multi-hop flow that desperately needs tracing.

**(b) Recommendation.**

- **Structured logs** (JSON) with `trace_id, restaurant_id, actor_id, event_type`.
- **OpenTelemetry**: instrument Django, Channels consumers, Postgres, Stripe SDK, Redis. Propagate `traceparent` through WS frames (custom envelope field) so a front-end "tap" can be traced into a back-end commit.
- **RED metrics** per endpoint and per WS event type. Histogram for `payment_intent.succeeded → kitchen.ticket.created` lag.
- **SLOs**:
  - p95 floor-plan-repaint server emit < 50 ms.
  - p95 KDS tap → waiter update < 250 ms end-to-end.
  - Webhook → Kitchen Ticket creation < 1 s, success ≥ 99.9 %.
- **Audit log** is separate from operational logs and immutable (append-only table, hash-chained).
- **Alerts**: outbox lag, Stripe reconciliation drift, WS group fan-out errors, Channels worker queue depth.

**(c) Priority: H.**

---

## 13. Security

**(a) Missing.**

- JWT refresh strategy unspecified (AC says token invalidates on role change — how? denylist? short-lived + rotation?).
- QR codes: spec says "scan QR → identify restaurant and table". A naked table-id URL invites replay (someone takes a photo of the QR and orders from across town).
- Webhook endpoints: Stripe handles HMAC, but no mention of CSRF posture or IP allowlist.
- PII: customer names, phone, payment method tokens — no encryption-at-rest discussion.
- Photo/menu media: where served from? signed URLs?
- Audit immutability: Feature 11 AC3 forbids external write on financial records but the *internal* audit trail has no immutability story.
- Session fixation: if a guest closes the tab and another guest scans the same QR, do they inherit state?

**(b) Recommendation.**

- **JWT**: short-lived access (10 min) + rotating refresh (7 days, sliding) stored in HttpOnly Secure SameSite=Strict cookie. Revocation via `jti` denylist in Redis, TTL = access lifetime.
- **QR tokens**: signed table token `qr.<rid>.<tid>.<exp>.<sig>` rotating daily; on scan, server issues a session-scoped guest JWT bound to `(table_id, device_fingerprint)`. Compromised QR expires within 24 h.
- **Webhooks**: dedicated route, CSRF-exempt, signature verification mandatory, IP allowlist for Stripe published ranges, replay window 5 min.
- **PII**: encrypt phone, name at rest with `pgcrypto` or app-level KMS-backed envelope encryption; redact logs.
- **Audit log**: append-only table, weekly checkpoint hash anchored externally (e.g., S3 Object Lock or notarized).
- **Media**: store in object storage; serve via CDN with signed short-lived URLs for staff-only assets.
- **Session takeover protection**: tie guest session to `device_fingerprint`; on QR re-scan from a different fingerprint, prompt confirmation.

**(c) Priority: H.**

---

## 14. Testing Strategy

**(a) Missing.** No test pyramid mentioned. AC are functional. For a real-time multi-actor system, contract tests on WS events and integration tests on digital handshakes are non-negotiable.

**(b) Recommendation.**

- **Unit**: FSM transitions (per axis 2), pricing/tax math, permission matrix evaluation.
- **Contract**: JSON-schema each WS event; CI fails if producer/consumer drift. Generate TS types (Feature 0 AC3) from the same schema source of truth.
- **Integration**:
  - Stripe webhook → Outbox → Kitchen Ticket → Channels broadcast (use Stripe CLI fixture events).
  - Cook claim race: two parallel POSTs on same ticket → exactly one wins.
  - Reconnect replay: drop WS, mutate state, reconnect, assert events arrive in order.
- **E2E**: Playwright across Waiter + Cook + Client tabs in one test, asserting the floor-plan ripples within SLO.
- **Load**: locust on the WS fan-out: 50 tablets × 200 events/min, assert p95 latency.
- **Chaos**: kill Redis mid-bump, kill Daphne mid-broadcast — outbox drain must catch up.

**(c) Priority: H.**

---

## 15. API Style: REST + WS

**(a) Missing.** Spec mixes REST and WS without a convention. Some flows (Approve & Fire) could be either. Risk: drift between "what state-changing endpoint exists" and "what event fires".

**(b) Recommendation.** Adopt **command/query split**:

- **Commands** (state changes): REST `POST/PATCH/DELETE` returning the new resource version. Server emits the canonical event on success. Clients never write WS frames — WS is **read-only**.
- **Queries** for initial load and refetch: REST `GET`.
- **Sync stream**: WS for live deltas + reconnect replay (axis 5).
- Each command response includes the `event_id` it emitted, so a client can correlate its optimistic update with the broadcast.
- One OpenAPI spec (drf-spectacular is already in deps) + one AsyncAPI spec for WS; both are sources of truth for codegen.

**(c) Priority: M.**

---

## Recommended Data-Model Additions (Schema Sketches)

Minor units integer money, `restaurant_id` everywhere implied.

| Entity | Key Fields | Notes |
|---|---|---|
| `Reservation` | id, restaurant_id, table_id (nullable until assignment), guest_user_id?, guest_name, guest_phone_enc, party_size, start_at, end_at, status (FSM), source (qr/web/phone), confirmation_code, version | Phase 2 booking; status: PENDING/CONFIRMED/CHECKED_IN/CANCELLED_*/NO_SHOW |
| `MenuCategory` | id, restaurant_id, name, sort_order, active | Phase 4 Pantry |
| `MenuItem` | id, restaurant_id, category_id, name, description, price_cents, currency, tax_class_id, image_url, is_active, is_86, station_id, allergen_ids[], version | `is_86` distinct from `is_active` |
| `MenuItemVariant` | id, menu_item_id, name, price_delta_cents | e.g., size S/M/L |
| `ModifierGroup` | id, restaurant_id, name, min_select, max_select | "Sauces", "Doneness" |
| `Modifier` | id, modifier_group_id, name, price_delta_cents | |
| `MenuItemModifierGroup` | menu_item_id, modifier_group_id, required | M2M |
| `Allergen` | id, code (gluten/dairy/…), label | EU regs |
| `Tax` | id, restaurant_id, name, code | Group of rates |
| `TaxRate` | id, tax_id, percent, effective_from, effective_to | Time-versioned |
| `OrderItem` (extend) | + modifier_selections jsonb, guest_seat_id, fired_at, ready_at, served_at, voided_at, void_event_id, status (FSM) | |
| `OrderItemTaxLine` | order_item_id, tax_id, rate_percent, taxable_cents, tax_cents | Snapshot at fire-time |
| `GuestSeat` | id, session_id, label ("Seat 1") | Phase 4 Waiter |
| `Payment` | id, order_id, provider (stripe), provider_payment_intent_id, amount_cents, currency, status (FSM), idempotency_key, captured_at, version | Multiple per order |
| `Refund` | id, payment_id, amount_cents, reason, provider_refund_id, status, created_at | |
| `Dispute` | id, payment_id, amount_cents, provider_dispute_id, status, opened_at, resolved_at | |
| `VoidEvent` | id, order_item_id, reason_code, is_wasted, actor_id, at, amount_cents | Immutable |
| `WasteLog` | id, restaurant_id, menu_item_id, qty, reason, source (void/spoil/training), at | |
| `Inventory` | id, restaurant_id, sku, on_hand, par, unit | Optional but recommended |
| `Discount` | id, restaurant_id, code, kind (percent/amount), value, scope, validity | |
| `OrderDiscount` | id, order_id, discount_id, amount_cents, actor_id | |
| `Shift` | id, restaurant_id, staff_id, clock_in, clock_out, role_at_shift | |
| `TipDistribution` | id, shift_id, amount_cents, source_order_id? | |
| `LayoutVersion` | id, restaurant_id, parent_version_id, layout_json, published_at, published_by, version_label | Immutable history |
| `FloorSection` | id, restaurant_id, name | "Main Hall", "Terrace" |
| `TablePlacement` | id, layout_version_id, table_id, x, y, w, h, rotation, section_id | Per-version geometry |
| `MergedTableGroup` | id, session_id, table_ids[] | Merge for parties |
| `Ticket` (extend) | + station_id, claimed_by, claimed_at, bumped_at, recalled_at, parent_ticket_id?, version | Multi-station support |
| `KitchenStation` | id, restaurant_id, name, printer_route | Grill/Cold/Bar |
| `Notification` | id, restaurant_id, target_role/staff/user, kind, payload, created_at, read_at | Persisted stream |
| `AuditLogEntry` | id, restaurant_id, actor_id, entity_kind, entity_id, action, before, after, hash, prev_hash, at | Hash-chained |
| `EventLog` | id (ULID), restaurant_id, type, payload, occurred_at, channels[] | Replay source |
| `Outbox` | id, aggregate_kind, aggregate_id, event_type, payload, created_at, dispatched_at | Pattern |
| `IdempotencyKey` | key PK, request_hash, response_json, created_at, ttl | Per axis 4 |
| `Receipt` | id, session_id, immutable_json, pdf_url, issued_at, hash | History feed |
| `Review` | id, restaurant_id, user_id, session_id?, rating, body, created_at | Scenario B |
| `Device` | id, restaurant_id, kind (kds/waiter), name, last_seen | Observability |
| `Role`, `Permission`, `RolePermission`, `StaffRole` | … | Per axis 8 |

---

## Prioritisation Summary (H/M/L)

**H** — axes 1, 2, 3, 4, 5, 6, 7, 8, 11, 12, 13, 14.
**M** — axes 9, 10, 15.
**L** — (none; spec gaps are uniformly material).
