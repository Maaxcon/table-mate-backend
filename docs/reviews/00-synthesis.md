# TableMate Workflow Doc — Cross-Role Review Synthesis

> Source review files in this folder: [Client](01-client.md), [Waiter](02-waiter.md), [Kitchen](03-kitchen.md), [Admin/Manager](04-admin.md), [Owner](05-owner.md), [Architecture](06-architecture.md), [Competitive landscape](07-competitive-landscape.md).
> Reviewed document: [`docs/architecture-and-workflows.md`](../architecture-and-workflows.md).
> Method: seven independent agents — five role hats (client/waiter/cook/admin/owner), one architecture audit, one competitive scan across 30+ products (Toast, Square, TouchBistro, Lightspeed K, Clover, Revel, OpenTable, Resy, SevenRooms, Tock, Eat App, Fresh KDS, Oracle Simphony, Toast KDS, Square KDS, Sunday, Mr Yum, GloriaFood, Bbot/DoorDash, Flipdish, BentoBox, SoluM, Tabesto, Yoello, MyCheck, Adyen, Yelp Guest Manager…). Each agent built its own concrete fix list; this file is the cross-cut.

---

## TL;DR

**What the spec gets right.** Prepay-only client orders, atomic per-item dish lifecycle (gray → yellow → green) with real-time WebSocket pulse back to the floor plan, cross-ticket Batch View, immutable versioned floor-plan publish, role-scoped WS broadcast with reconnect replay, "no Call Waiter to Order" anti-abuse rule, immutable financials. These are competitive choices and should stay.

**What it gets wrong.** It is a **kitchen-flow + QR-ordering MVP**, not a restaurant product. It optimises the 10% of a manager's shift that involves looking at a screen, and ignores the 90% that involves money, people, recovery, and edge cases. The diner spec breaks the moment the diner is not a logged-in solo Google-account adult with one card paying for one set of dishes. The kitchen spec collapses on the first multi-station service. The architecture is silent on every concurrency, replay, payment-edge, multi-tenancy, and audit problem that this kind of real-time multi-actor system *will* hit in week 1.

**Verdict.** Don't ship the spec as-is to a real venue. Roll the H1 items below into the [Speckit constitution](../../.specify/memory/constitution.md) / spec changes before the next pilot, and the H2 items before any second venue or any chain customer.

---

## Themes that 4+ reviewers independently raised

These are the cross-cutting holes — fix any one of them in isolation and three roles say "thanks".

| # | Theme | Raised by | Where it bites |
|---|---|---|---|
| 1 | **Allergens are free-text comments** | Client, Waiter, Kitchen, Architecture, Owner, Competitive | EU 1169/2011 violation; legal liability on first incident; line cook can miss "NUT ALLERGY" in a comment box at 8pm Saturday |
| 2 | **No tipping / settlement / split-bill / cash anywhere** | Client, Waiter, Admin, Owner, Competitive | The word *tip* does not appear in the doc. Spec ends at "bill is paid" with no UI for paying. 25–40% of EU revenue is cash. Tip-pool calculation is regulated (UK Allocation of Tips Act, etc.) |
| 3 | **Comp ≠ Void ≠ Discount — collapsed into a single Void flow** | Admin, Owner, Architecture, Competitive | Fiscal certification fails in CH (MWST/TSE), DE (KassenSichV), IT (lotteria), FR (NF525) when comp/void/discount are not separable, and managers fall back to off-system workarounds (fraud risk) |
| 4 | **Course pacing is absent — apps and mains fire together** | Waiter, Kitchen, Competitive | Every ticket lands cold mains next to half-eaten apps. Lightspeed K, Toast, Fresh KDS all have course-firing |
| 5 | **No per-station KDS routing — one global Incoming column** | Kitchen, Architecture, Competitive | A 12-station kitchen sees 12× the noise; unusable above bistro scale. Toast/Square/Lightspeed/Oracle all ship station routing |
| 6 | **86-from-KDS is missing (admin-only "Sold Out" toggle)** | Waiter, Kitchen, Owner, Competitive | The sauté cook knows we're down to two salmon before the manager does. Forcing admin-only toggling causes "I just took 3 salmon orders" embarrassment |
| 7 | **No section/zone assignment for waiters** | Waiter, Architecture, Competitive | "Table 12 is requesting a waiter" → to whom? Either every waiter gets pinged (noise) or no one does (15-min ignore). OpenTable, Square, Eat App all have section assignment |
| 8 | **Hard-disable on WS drop is a kitchen-killer** | Kitchen, Owner, Architecture, Competitive | Feature 12 AC2 disables all writes when offline; line freezes on a 10s wifi blip. Toast, Oracle KDS keep local caches |
| 9 | **No multi-venue / Organization → Brand → Venue hierarchy** | Admin, Owner, Architecture, Competitive | Caps the product at single-shop. No central menu, no cross-venue staff, no rollup P&L |
| 10 | **No reservation deposit / no-show fee / waitlist** | Client, Admin, Owner, Competitive | Tock built a business on this; OpenTable/Yelp ship waitlist+SMS. TM's prepay-only philosophy applies *perfectly* to bookings but isn't used there |
| 11 | **No loyalty / marketing / CRM** | Client, Owner, Competitive | "Identity & Loyalty" defines only a join date. Repeat visits are 5–10× cheaper to acquire than new diners; this is the cleanest revenue lever and it's missing |
| 12 | **No table merge / transfer / split** | Waiter, Architecture, Competitive | Every weekend two 4-tops get pushed together; spec has no concept |
| 13 | **No accessibility / WCAG / colour-redundancy** | Client, Competitive | Free/Occupied/Reserved by colour only is a WCAG fail; ~8% of male diners can't distinguish gray-yellow-green. EU EAA 2025 makes this a legal floor |
| 14 | **No immutable hash-chained audit log** | Admin, Owner, Architecture | Required for fiscal regulators, labour disputes, insurance. "Void Audit Trail" is a *report*, not an *audit log* |
| 15 | **No structured modifiers — comment-only Modifier Modal** | Waiter, Kitchen, Architecture, Competitive | "No onions" + "extra onions" both print to the line; "medium rare, extra sauce" is line-cook roulette |
| 16 | **No course/refire/recall-from-completed** | Kitchen, Competitive | A returned steak isn't a Void; it's a Refire with no-charge. Voids and refires aren't the same thing |
| 17 | **No proper data model for state machines** | Architecture | ENUMs without transition rules let any handler corrupt state. Need Table/Session/Order/OrderItem/Ticket/Payment/Reservation FSMs codified |
| 18 | **No payment edge cases (refund, dispute, partial capture, late webhook, 3DS)** | Architecture, Owner | Feature 4 covers happy path only |
| 19 | **No multi-tenancy enforcement** | Architecture | Every entity needs `restaurant_id`; JWT must carry `allowed_restaurant_ids`; RLS + tenant-scoped DRF queryset as defence-in-depth |
| 20 | **No WS event catalog / idempotency contract / outbox** | Architecture | "At-least-once" is promised but has no mechanism. Stripe webhook can double-fire kitchen tickets without `idempotency_keys` table + outbox pattern |

---

## H1 — Blocking. Must land before next pilot

Each row is concrete and traceable to at least one role's review. Where multiple reviews proposed the same fix, the H/M/L is the highest across them.

| # | Improvement | Touches | Source reviews |
|---|---|---|---|
| 1 | **Promote allergens to first-class.** `Allergen` entity + M2M to `MenuItem`; `dietary_flags[]` on `GuestSeat`; sticky red banner in Modifier Modal; allergy-distinct audio cue + red-border render on KDS; mandatory `Acknowledge Allergy` tap before `Start Item`; expo re-confirm at pass (marine-bridge second-check). Also: allergen profile on User account (Phase 3) so it auto-attaches to every order. | Client P3, Waiter P4 + F5, Kitchen P1, Admin compliance, Architecture data model | 01, 02, 03, 04, 06, 07 |
| 2 | **End-to-end Settlement (new Waiter Phase 6).** Split modes (even / by-seat / by-item), per-bucket tender (card/cash/Apple/Google/comp/house-account), `Payment` entity with FSM and many-per-order cardinality. Webhook is sole source of truth for `Payment.status`. Stripe `Idempotency-Key = "pay:<order_id>:<attempt_uuid>"`. Daily reconciliation job. | Waiter P6 (new), Architecture payments, Owner ROI, Admin cash | 02, 04, 05, 06 |
| 3 | **Tipping model.** `tip_amount`, `tip_method (card/cash)`, `service_charge_amount` on `Payment`. `tip_pool` config per restaurant (`none | section | shift | role_weighted`). End-of-shift Tip Report with sign-off + audit. Tip attribution to authenticated server (Adyen/Toast pattern, also a tax-law requirement in several jurisdictions). | Waiter, Admin, Owner, Competitive | 02, 04, 05, 07 |
| 4 | **Comp / Discount / Void as three separate entities** with their own lifecycles, reason codes, tax treatments. Pre-fire / post-fire / post-serve void stages. Comp stages: `cost_center`, `attributed_to_staff_id`, `tax_treatment`. Approval matrix table: `(role, action_type, single_value_cap, daily_cap, requires_dual_auth_above, requires_owner_notify_above)`. Server's tablet shows "Awaiting manager" lock; manager swipe/PIN releases. | Admin P2, Architecture, Owner fiscal, Competitive | 04, 05, 06 |
| 5 | **Course pacing.** `OrderItem.course` (App/Main/Dessert/Side) + `fire_when` (Immediate/Hold/On-Cue). New `HELD` column on KDS. "Fire Course 2" button on table view, optionally auto-fired when course 1's last item is `served`. `auto_fire_after_seconds` config per course. | Waiter P3, Kitchen P2, Competitive (Lightspeed K, Fresh KDS) | 02, 03, 07 |
| 6 | **Per-station KDS routing.** `KitchenStation` entity. `MenuItem.station_id` (or `prep_routes[]` for multi-station items like a burger = grill+fry). Each station screen filters Active/Incoming items by station. **Add `Expediter` role** (`Role.Expediter` in RBAC), with full-ticket view across stations and exclusive `BUMP` authority (cook-only bump is a per-restaurant toggle for small kitchens). New `Plated` lifecycle state between item-Green and ticket-Bumped. | Kitchen P1, Kitchen P4, Architecture RBAC, Competitive (Toast, Square, Lightspeed, Oracle) | 03, 06, 07 |
| 7 | **Cook-initiated 86 with retroactive impact modal.** "Mark 86" button on Kitchen Kanban item card (long-press). Two modes: `Set Count Remaining: N` (auto-86 when waiter orders the Nth) and `86 Now`. Blocking Waiter modal listing affected drafts and in-flight tickets with per-row `Suggest substitute / Remove / Notify guest`. WS event `inventory.item.eighty_sixed`. Manager notified, not bottleneck. | Waiter P4, Kitchen P6, Competitive (Fresh KDS) | 02, 03, 07 |
| 8 | **Section assignment + section-scoped WS events.** `ShiftAssignment` model (`waiter_id, section_id, start_at, end_at`). Waiter token receives `order.*` and `table.request.*` events only for tables in current section (+ a "Backup waiter" overflow rule). Floor plan default-filters to the waiter's section with `Show full floor` toggle. Out-of-section tables render at 30% opacity, untappable except by Manager. | Waiter P1, Architecture WS catalog, Competitive (OpenTable) | 02, 06, 07 |
| 9 | **Hash-chained `ManagerActionLog` (append-only).** Every void/comp/discount/price-override/refund/cash-drop/schedule-edit row carries `prev_hash` HMAC. No `UPDATE/DELETE` grants at DB role level. Surface inside Manager UI as "Table 7 history" tab. This satisfies fiscal regulators + labour disputes + insurance simultaneously. | Admin P3, Architecture security/audit, Owner compliance | 04, 05, 06 |
| 10 | **Multi-tenancy enforced two layers deep.** Every entity (except global lookups) has `restaurant_id NOT NULL` + composite indexes. JWT: `{ sub, role, restaurant_id, allowed_restaurant_ids[] }`. Tenant-scoped DRF queryset (`TenantScopedManager`) **plus** Postgres RLS (`SET LOCAL app.restaurant_id`). Channels groups always prefixed `rst:<rid>:…`, validated at WS connect. Chaos test drops `request.tenant` and verifies zero rows returned. | Architecture, Owner multi-venue, Admin chains | 04, 05, 06 |
| 11 | **Codify the FSMs.** Table / Session / Order / OrderItem / Ticket / Payment / Reservation each get an explicit FSM (states + allowed transitions + actor guards) in `apps/<domain>/state.py` with a single transition function that emits the canonical WS event. ENUM at DB + FSM in code, both required. | Architecture | 06 |
| 12 | **WebSocket event catalog + idempotency + outbox.** Typed envelope (`{id ULID, type, version, restaurant_id, occurred_at, actor, idempotency_key, data}`), explicit channels (`rst:<rid>:floor`, `rst:<rid>:kds:<station>`, `rst:<rid>:table:<tid>`, …), AsyncAPI source-of-truth, TS codegen. Outbox table; single worker copies `outbox → event_log → Channels group_send`. Per-client `last_event_id` cursor on (re)connect. `idempotency_keys(key PK, request_hash, response_json, ttl)` table for all `POST/PATCH/DELETE` and webhooks. | Architecture (3, 4, 5) | 06 |
| 13 | **Payment edge cases.** Webhook is **sole** source of truth for `Payment.status`. Stripe `Idempotency-Key` everywhere. Handle `requires_action` / 3DS, `processing`, `payment_failed`, `amount_capturable_updated`, `charge.refunded`, `charge.dispute.created`. `Refund` + `Dispute` entities, write-only ledger — never mutate prior `Payment`. Daily reconciliation job vs Stripe `balance_transactions`. Late-webhook policy: `PaymentOrphaned` audit row + auto-refund job. | Architecture, Owner | 05, 06 |
| 14 | **Money model.** Integer minor units (`amount_cents INTEGER`, `currency CHAR(3) ISO-4217`). Never float. `Tax`, `TaxRate` (effective-from/to), `OrderItemTaxLine` snapshot rate at fire-time. `tax_inclusive` per restaurant. Bankers' rounding for tax lines; document and unit-test. Tip is a separate line. | Architecture, Owner EU fiscal | 05, 06 |
| 15 | **Cash handling.** `Till`, `TillSession`, `CashDrop`, `CashCount`, `CashOverShort`. `Cash` as a first-class `payment_method` on `Payment` with the same fiscal-receipt requirements as card. Blind cashout flow (server enters counted amount; variance shown to manager first, then server). Trend per server. Daily safe drop, weekly bank deposit reconciliation. | Admin P5, Owner | 04, 05 |
| 16 | **Fiscal reporting suite.** Daily Z-Report (gross sales by tax rate, by category, by tender, voids/comps/discounts, employee meals, no-show fees) with fiscal signature. Daily X-Report (mid-day, non-fiscal). VAT report (with eat-in vs takeaway split for CH/DE). Accounting exports: Xero, QuickBooks, Sage, Bexio (CH), Abacus (CH), DATEV (DE). Retention 7 years. | Admin P5, Owner | 04, 05 |
| 17 | **GDPR + EU 1169/2011 compliance.** `Customer.privacy_state: active | anonymization_requested | anonymized`. DSAR export (JSON) + erasure (PII fields → NULL/hash, fiscal records preserved). Consent log (immutable). Allergen schema on every `MenuItem` (`allergens[]`, `may_contain[]`, `nutritional_info`, `last_updated_at`, `responsible_staff_id`). Age-gate on alcohol items. | Admin P10, Owner, Client P10 | 01, 04, 05 |
| 18 | **Offline-first KDS + waiter (with hard limits).** Distinguish **safe-offline writes** (KDS tap "Item Ready", BUMP) from **unsafe** (Close Table, Pay, Publish Layout). Safe ones into a local write-ahead queue (Service Worker + IndexedDB) with optimistic UI; replay with idempotency keys on reconnect. ESC/POS printer fallback over LAN for KDS when WS server unreachable. Hard-disable + banner remains for unsafe writes only. | Architecture, Owner, Kitchen | 03, 05, 06 |
| 19 | **Apple Sign-In, email magic link, phone OTP, full i18n.** Google-only OAuth is an App Store violation if shipped on iOS. Locale auto-detected from device; menu/modifiers/allergens/notifications all run through translation layer. Currency formatting per locale. | Client P5 | 01 |
| 20 | **Accessibility / WCAG 2.2 AA.** Non-colour status redundancy (icon + label on every Free/Occupied/Reserved tile and every Gray/Yellow/Green dish state). Accessibility tags on tables (wheelchair, step-free, low-noise, near-restroom) filterable in Phase 2. Alternative list-view to the spatial floor plan. Captions + haptics for every audio chime. EU EAA from June 2025 — legal floor. | Client P10, Architecture | 01, 06 |
| 21 | **Observability + SLOs.** Structured JSON logs (`trace_id, restaurant_id, actor_id, event_type`). OpenTelemetry across Django, Channels, Postgres, Stripe, Redis. Propagate `traceparent` through WS frames. Concrete SLOs: p95 floor-plan repaint server-emit < 50ms, p95 KDS tap → waiter update < 250ms end-to-end, webhook → Kitchen Ticket < 1s at ≥99.9%. | Architecture | 06 |
| 22 | **Security baseline.** Short-lived access JWT (10min) + rotating refresh (7d, sliding) in `HttpOnly Secure SameSite=Strict` cookie. Revocation via `jti` denylist (Redis). QR token signed + rotating daily (`qr.<rid>.<tid>.<exp>.<sig>`) — no naked table-id URLs (replay attack vector). PII at rest encrypted (`pgcrypto` / KMS). Audit log weekly hash anchored externally (S3 Object Lock). | Architecture | 06 |
| 23 | **Contract + integration tests for the digital handshakes.** JSON-schema each WS event in CI; producer/consumer drift fails build. Generate TS types from the same schema. Stripe webhook → Outbox → Kitchen Ticket → Channels broadcast integration test (Stripe CLI fixtures). Cook claim race test (two parallel POSTs → exactly one wins). Reconnect-replay test. | Architecture | 06 |

---

## H2 — Should land before second venue or any chain customer

| # | Improvement | Touches | Source reviews |
|---|---|---|---|
| 24 | **Reservation deposits + no-show fee + waitlist** (Tock model — perfectly aligned with TM's prepay philosophy). `Reservation.deposit_amount`, `deposit_state (held|captured|refunded|forfeited)`, `late_release_minutes`, `no_show_policy_text` versioned & accepted at booking. Stripe SetupIntent for hold. Walk-in waitlist with SMS-when-ready. Customer flags: VIP, blacklist, no-show count. | Client P9, Admin P7, Owner, Competitive (Tock, OpenTable) | 01, 04, 05, 07 |
| 25 | **Loyalty + marketing + post-visit review prompts.** Configurable accrual (e.g., 1pt/€1), redemption ladder, optional tiers, birthday auto-credit. Segments ("haven't visited in 45 days", "spent > €200 lifetime"). Send via SendGrid/Twilio with double opt-in. Post-visit review prompt 60–120 min after `session.closed`: 4–5★ → deep-link to Google review; 1–3★ → internal feedback ticket routed to manager (review-deflection pattern). | Owner, Client P6, Competitive (BentoBox, SevenRooms, Sunday) | 01, 05, 07 |
| 26 | **Multi-venue: Organization → Brand → Venue hierarchy.** `Staff` has many `VenueMembership` rows with role-per-venue. Central `MenuTemplate` at Brand level, `MenuOverride` at Venue level with audit on overrides. Cross-venue dashboard: revenue, prep-time, void rate, table turn side-by-side. Top-bar "Switch context" with current scope persistently visible. | Admin P8, Owner P6, Architecture | 04, 05, 06 |
| 27 | **Group/party model + Group Tab.** Booking creates a Party object with invite code; guests join via deep link (lifts the Scenario B live-order block for confirmed party members). Each guest gets own cart that merges at Phase 4 Checkout. "Guest Slots" become real client-side entities, not just waiter-side. Mr Yum's Group Tab pattern: multiple phones one table one open tab. | Client P2, Waiter P4, Competitive (Mr Yum, Bbot) | 01, 02, 07 |
| 28 | **Modify-after-fire flow ("Add to order").** Phase 4-style mini-checkout from the active session screen; new items become a child ticket injected at current timestamp into Kitchen Incoming. Items in Yellow/InProgress cannot be removed without admin Void; Gray/Pending items can be canceled client-side. Replaces the deleted "Call Waiter to Order" fallback with a sanctioned digital path. | Client P8 | 01 |
| 29 | **Cancellation, refund, no-show policy engine.** Phase 2 modify/cancel surfaces explicit policy ("Cancel free until 18:00, then 50% fee"); cancellation fires a Void event to KDS (reusing Feature 7 atomic). `RefundState` on Order. Reservations require card-hold for prime slots; auto-release after grace period; no-show fee charged. Receipts/refund-receipts to email + in-app history. | Client P7, Admin P7 | 01, 04 |
| 30 | **Refire / recall workflow.** New action `Refire(item_id, reason_code, no_charge: bool)` distinct from Void. Reason codes: GuestReturn, DroppedInKitchen, WrongDoneness, Allergen, Mispick, RushReplace. Creates a new `OrderItem` linked via `refire_of` FK; KDS badge "REFIRE — DO NOT REBILL"; refires jump station queue with distinct red border. Plus `Ticket → RECALLED` state for fetching a bumped ticket back. | Kitchen P5, Architecture FSM, Competitive (Fresh KDS, Oracle) | 03, 06, 07 |
| 31 | **Merged-table (`TableGroup`).** Long-press multi-select on map → Merge; single Session across multiple tables; dotted-hull rendering; KDS ticket header "T-04+05". Atomic un-merge on Close. WS events `table.merged` / `table.unmerged`. | Waiter P2, Architecture | 02, 06 |
| 32 | **Structured modifiers.** Menu Item schema gains `modifier_groups` (e.g., Steak has `Doneness` required-one-of, `Sauce` multi-select, `Sides` radio). Modifier Modal renders structured controls **above** the free-text comment. Server rejects mutually exclusive modifier values at order-submit (`409 ModifierConflict`). KDS renders modifiers as colour chips: negatives red ("NO onion"), additions green ("+bacon"). | Waiter P12, Kitchen P13, Architecture | 02, 03, 06 |
| 33 | **Shift lifecycle.** `Shift`, `ShiftSegment`, `Break`, `ShiftSwapRequest`. Clock-in/out (optionally geofence or QR at host stand). Legally mandated break tracking (Switzerland ArG Art. 15 etc.). Open shift marketplace. Overtime warnings *before* not after. Payroll exports (Bexio, Abacus, ADP, Gusto) with cost-center splits. | Admin P4, Owner | 04, 05 |
| 34 | **Inventory engine.** `Ingredient` (unit, cost, supplier, lead time, par level). `Recipe` linking MenuItem → list of `(Ingredient, qty, unit, yield_factor)`. On every `BUMP`: decrement stock via outbox → inventory service. Auto-86 when projected stock < average sell-through to close. Daily variance: theoretical use vs actual count. Waste log aggregates `is_wasted` voids + manual entries → categorised weekly report. COGS% KPI per category. | Admin P6, Owner | 04, 05 |
| 35 | **Role split: ShiftManager / GeneralManager / Owner / Accountant / Auditor + Host / Expediter / Bartender / Busser / Trainee.** Replace role enum with a permission matrix (`Role —< RolePermission >— Permission`; `Staff —< StaffRole >— Role` with `restaurant_id` scope and validity window). Manager Override flow: PIN-gated elevation creating short-lived JWT (5 min) with extra scopes, fully audited. | Admin P12, Architecture RBAC, Competitive | 04, 06, 07 |
| 36 | **Waiter-initiated Void Request + separate Comp action.** New "Request Void" button on item card → Manager queue with high-priority WS alert → one-tap approval. Comp as distinct flow with own reason codes (Service Recovery / VIP / Marketing / Birthday / Staff Meal). Below per-restaurant threshold (e.g., €15), waiver auto-approved by waiter with daily cap. | Waiter P6, Admin | 02, 04 |
| 37 | **Shift handover.** Per-Session free-text "Handover Notes" + structured "Open Tasks" checklist on Table Detail Overlay. "Reassign Waiter" action; pre-shift "Inherited Tables" dashboard with notes pinned. | Waiter P5 | 02 |
| 38 | **Per-item `prep_minutes` + backwards timing.** Compute `target_pickup_at = max(item.prep_minutes for items in same course on ticket)` at fire-time. Per item show `start_by = target_pickup_at − item.prep_minutes`. Station screen sorts by `start_by`, not injection timestamp. Items past `start_by` flash amber. | Kitchen P3, Competitive | 03, 07 |
| 39 | **Late-ticket dwell + escalation tiers on KDS.** Each KDS card shows `elapsed_since_fired` (mm:ss) top-right. Visual escalation tiers configurable per restaurant: green 0-target, amber target → target×1.25, red target×1.25+. Flash at target×1.5. WS event `ticket.late` notifies expo + manager. | Kitchen P12, Competitive (Toast KDS, Oracle) | 03, 07 |
| 40 | **Partial / per-course bump + runner notifications.** Item-level bump remains, ticket-level BUMP closes the whole. "Partial Bump" per course so runner can pick up the apps without waiting on mains. Runner queue groups ready items by table; Hot/Cold class; "Run" grouping for batched trips. Coalesce simultaneous Greens: 4 in 5s → one expandable group. | Kitchen P8, Waiter P11 | 02, 03 |
| 41 | **Concurrency primitives.** Optimistic concurrency `version BIGINT` on Table, Session, Order, OrderItem, Ticket, Layout — `If-Match` rejection on mismatch. Pessimistic where short: `SELECT … FOR UPDATE SKIP LOCKED` on Ticket claim — first cook wins, others get 409. Distributed Redis lock for Layout publish + `LayoutVersion.parent_version_id` for CAS. | Architecture | 06 |
| 42 | **REST + WS convention: commands as REST, WS read-only.** Commands (state changes) are REST `POST/PATCH/DELETE` returning new resource version; server emits canonical event on success. Queries via REST `GET`. WS is read-only deltas + reconnect replay. Each command response includes the `event_id` it emitted so a client correlates its optimistic update with the broadcast. OpenAPI (drf-spectacular already deps) + AsyncAPI; both source of truth. | Architecture | 06 |
| 43 | **Data export + portability + menu import.** `GET /export/{entity}.csv` + one-click full account export (also satisfies GDPR Art. 20). Menu import CSV + Square/Toast/Lightspeed mapper. Data ownership clause in spec: owner owns menu, orders, customer records collected at their venue. | Owner | 05 |
| 44 | **Customer complaint routing.** Negative review (≤3★) within venue or within X hours of session close → high-priority push to manager on duty with full session context (table, server, items, total, void/comp history). Manager UI "Open Complaints" inbox with SLA timer. Reply path can comp/refund/voucher from the complaint card. Aggregate: 3+ negative reviews for same dish in a week → flag to chef. Optional 1-hour cooling-off hold before public publication. | Admin P14, Owner | 04, 05 |
| 45 | **Integrations roadmap with named partners.** Accounting (Xero, QuickBooks, Sage, Bexio, Abacus, DATEV); HR/scheduling (Deputy, 7shifts, Sling); delivery (Uber Eats, Deliveroo, JustEat, DoorDash) with menu sync + order ingest into KDS; inventory (MarketMan, Apicbase); reservations (OpenTable, TheFork, Google Reserve); marketing (Mailchimp, Klaviyo); BI (Looker, Metabase). Public REST + webhook API with OAuth2 client credentials. Marketplace UI in Admin. | Owner, Competitive | 05, 07 |

---

## M — Strong post-MVP wins

| # | Improvement | Source |
|---|---|---|
| 46 | **Walk-in waitlist + virtual queue** with SMS/push "your table is ready"; pre-seat menu staging that fires on QR scan at the table | 01, 07 |
| 47 | **Favourites, "My Usual", reorder from History, loyalty tier visible** on Phase 3 Profile | 01 |
| 48 | **Dietary filters + rich menu UX** (vegan/GF/halal/kosher toggles, EU-14 allergen icons, calorie/macro, spice level, photo-required, search) | 01, 07 |
| 49 | **Push/SMS comms to the diner**: order-fired confirmation, order-ready notification, reservation reminders | 01 |
| 50 | **Pickup Queue + alert coalescing** for rush triage on the waiter app | 02 |
| 51 | **Auto-fire vs Approve & Fire** per-restaurant config + per-session override toggle + 30s "Auto-firing in 0:28 — tap to Hold" countdown on prepaid orders | 02 |
| 52 | **Training mode / sandbox.** `is_training` flag per session — orders don't inject to kitchen, no WS to real cooks, no financial records. Watermark visible on every screen. | 04 |
| 53 | **Tablet resilience.** Server-side draft autosave on every Modifier Modal submit. Staff PIN (6 digits) on top of admin-issued device token. Auto-lock after 60s inactivity. "Tablet Lost" action in Admin invalidates device token, fires WS so the missing tablet shows wipe screen. Per-action audit log: who-did-what-from-which-device. | 02 |
| 54 | **Kiosk mode** (locked-down full-screen Client UI on entry-stand iPad). Competitors report 20–30% AOV uplift. | 07 |
| 55 | **Move Table action.** Atomic session migration to a target Free table with `capacity >= party_size`; KDS tickets re-stamp with new table id; old + new tables fire WS updates. Capacity-overrun seating prompts "Seat anyway? (over by 1)" + flags session for manager. | 02 |
| 56 | **Brand customisation + custom domain** for the Client app (BrandTheme per Venue/Brand, CSS variables, `order.mybistro.com` via CNAME + auto-TLS) | 05 |
| 57 | **All-day production counts** ("all day, 14 ribeyes, 6 medium, 4 mr, 4 well") on KDS for grill batching | 03, 07 |
| 58 | **Audio token set** (`new_order`, `course_fired`, `allergy` distinct & loud, `refire`, `late_ticket` escalating, `void`, `bump_confirmed`); per-station volume; bump-bar USB-HID; greasy-finger tolerance (≥250ms hold for destructive actions, no swipe-to-delete) | 03 |
| 59 | **Recipe reference overlay on KDS** (long-press item → recipe overlay, non-destructive). `MenuItem.recipe_id` → ingredient list, method steps, plating photo, allergen content, default modifiers. | 03 |
| 60 | **Spatial-editor locking.** Pessimistic 5-min TTL lock when manager A enters Edit Mode; manager B sees "Currently being edited by Karen since 14:32 — request takeover?". Optimistic save with `expected_version`; conflict → diff UI. | 04 |
| 61 | **Multiple named floor plans** per venue (lunch vs dinner vs private event layouts) | 07 |
| 62 | **NFC tap-to-order at table** as alternative to QR (Yoello pattern) | 07 |
| 63 | **Delivery aggregator ingest** (Deliveroo / Uber Eats / DoorDash / JustEat via Deliverect or Otter) — tickets land in same Kanban with channel badge. 30–50% of revenue in many venues. | 07 |
| 64 | **Time / timezone done right.** All timestamps `TIMESTAMPTZ` UTC. `Restaurant.timezone` (IANA). `business_date` function maps timestamp → venue accounting day (cutoff 04:00 local) for daily KPIs. Reservations carry `(start_at_utc, end_at_utc, restaurant_tz)`. | 06 |
| 65 | **Upsell / cross-sell engine.** Rule-based first (item co-occurrence, margin-weighted), ML later. Inject into Client checkout and Waiter "add item" flow. Even 3% AOV lift on €60 cover at 1k covers/week = ~€90k/year margin. | 05 |
| 66 | **Chargeback evidence pack.** One-click bundle (order log, items served, timestamps, server name, IP, device fingerprint, signed receipt) → Stripe Dispute API submission. Post-visit Refund flow in Admin with reason code + partial amount + audit. | 05 |
| 67 | **Public-review syndication** (Google/TripAdvisor/TheFork) with private-first low-rating routing | 05, 07 |
| 68 | **Gift cards & vouchers** (digital + physical) | 07 |
| 69 | **Cover counts & pacing metrics on the floor plan** (per-server live cover count, OpenTable pattern) | 07 |

---

## L — Polish / can defer

| # | Improvement | Source |
|---|---|---|
| 70 | Pre-order ahead with fire-on-arrival for Scenario B, gated by deposit | 01 |
| 71 | Reviews v2: per-dish rating, waiter rating, anti-abuse rate-limit, public response from restaurant | 01 |
| 72 | Offline-tolerant client cart with retry queue (so a diner mid-checkout in a basement venue doesn't lose their order) | 01 |
| 73 | Guest-checkout lifecycle: receipt by email/SMS, post-visit "claim this order" link to upgrade to an account without losing history | 01 |
| 74 | Item-level photos for runners | 03 |
| 75 | Cook → waiter comm channel (cook can say "this duck will be 5 more, comp the table a starter?") | 03 |
| 76 | Reservation prep prewarn to kitchen (a 12-top in 30 min should pre-warn the line for mise) | 03 |
| 77 | HACCP / temperature logs / cleaning schedules | 04 |
| 78 | "Paper Mode" runbook: print-from-Admin daily snapshot of bookings + menu + prices so the venue can run on paper if the system is fully down | 05 |
| 79 | BNPL option for >€X tickets (Sezzle pattern) | 07 |

---

## What's genuinely differentiated and should stay

From the competitive scan and the architecture review, these are the bets that competitors do *not* combine and that TableMate should not water down:

- **Prepay-only enforcement** for client-led ordering (anti-dine-and-dash, no order-taken-wrong, payment cleared before fire). Apply the same philosophy to Reservations via H2 #24 deposits.
- **Atomic per-item dish lifecycle** with cross-system WS pulse (rare granularity — Toast/Square are ticket-level).
- **Batch View** aggregating identical items across tickets (almost no competitor ships this).
- **Immutable, versioned floor-plan publish** with WS hot-deploy + zero local inference.
- **Role-scoped WS broadcast** with reconnect replay (once the catalog + outbox of H1 #12 lands).
- **No "Call Waiter to Order" fallback** — a deliberate anti-abuse choice worth keeping (modify-after-fire H2 #28 is the right replacement, not bringing back the bypass).

---

## Suggested next steps

1. **Treat this synthesis as a backlog generator, not a spec.** Convert H1 rows into Speckit `specs/` work items (one per row or per group). The existing PR #2 (`chore/project-constitution`) is the right home for the policy/principles changes; the workflow doc itself (this PR) gets follow-up commits as decisions are made.
2. **Start with the entity model.** H1 #11 (FSMs), #12 (events/outbox), #14 (money), plus the entity tables sketched in [architecture review §"Recommended data-model additions"](06-architecture.md#recommended-data-model-additions-schema-sketches), unblock almost everything else.
3. **Get one role-end-to-end working first.** Pick Waiter, ship the section-assignment + course-pacing + structured-modifiers + settlement loop end-to-end before broadening. The current spec is wide and shallow; depth on one role validates the architecture under load.
4. **Pilot venue choice matters.** A cash-free, single-language, single-venue, table-service-only café will let H1 #15 (cash), #19 (i18n), #26 (multi-venue), #45 (integrations) slide further to the right. A multi-venue chain in CH/DE/IT/FR cannot.
