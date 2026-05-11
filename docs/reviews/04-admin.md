# TableMate — Admin/Manager Perspective Review

**Reviewer hat:** Restaurant Manager on duty (mid-size venue, ~80 covers, 6 servers, 1 GM + 2 floor managers).
**Scope:** PART 4 (Admin Workflow) + Phase 4 of Parts 1-3 where Admin/Manager intervenes.
**Verdict (TL;DR):** The spec describes a *technical control panel*, not a *manager's tool*. It is heavy on real-time UI mirroring and light on the everyday financial, HR, compliance, and recovery actions that consume 80% of a manager's shift. Below: scenario-by-scenario gaps and concrete fixes.

---

## 1. Comp vs Void vs Discount

**Spec coverage:** Phase 2 only defines **Void** (item correction, with Reason Code = Mispick/Quality/Out of Stock and a `is_wasted` boolean). No notion of Comp (free item, post-fire, service recovery) or Discount (line-level or check-level %/€ promo, loyalty, happy hour).

**Why it matters in real life:**
- **Void** = "the kitchen never should have made it / customer never received it." No revenue, possibly waste, item disappears from check.
- **Comp** = "kitchen made it, customer received/consumed it, we eat the cost as goodwill." Revenue line is shown then zeroed — for COGS, labor allocation, and *tax* this is NOT the same as a void.
- **Discount** = revenue is reduced but item was consumed; the discount itself is a tracked line for marketing attribution and tax base.

**Tax implications the spec ignores:**
- In most EU VAT regimes (incl. Switzerland MWST, German UStG, Italian IVA): a **void before fiscalization** removes VAT; a **comp after fiscalization** is a zero-rated sale with a separate "marketing/staff" expense — VAT may still be due on cost. Switching the wrong one creates an audit finding.
- Discounts must be itemized on the fiscal receipt with the discount type code (Switzerland: TSE/Kassensicherung-style requirements; Italy: lotteria scontrini codes; France: NF525).

**Concrete fixes:**
- Add three distinct entities: `Void`, `Comp`, `Discount` — each with its own table and lifecycle. Do NOT collapse into a generic "adjustment."
- `Void`: `reason_code`, `is_wasted`, `pre_fire | post_fire | post_serve` stage. Only `pre_fire` can be silent; the others require manager auth.
- `Comp`: `reason_code` (Service Recovery, Manager Promo, Birthday, Staff Meal, Marketing/Influencer), `cost_center`, `attributed_to_staff_id` (so it doesn't tank a server's check average), `tax_treatment` (gross-up vs net).
- `Discount`: `kind` (percentage | fixed | BOGO | loyalty | promo_code), `scope` (item | category | check), `stackable` (bool), `max_per_check`, `requires_code`, `applies_before_tax | after_tax`.
- Receipts must show original price, discount line, comp line, net — never just collapse to a single number, or your fiscal printer integration will fail certification.

---

## 2. Approval Thresholds

**Spec coverage:** Phase 2 says "Admin" can void with "elevated capabilities." Single role. No € threshold.

**Real-world reality:**
- A junior shift manager voids up to €20 alone. €20–€100 needs a co-signing manager. >€100 needs GM (often by phone if GM is off-site). >€500 needs owner notification.
- Comp budget per manager per shift is usually capped (e.g., €150/shift) and tracked against bonus/penalty.
- Repeat voids by the *same server* within X minutes should auto-escalate (fraud signal).

**Concrete fixes:**
- Add an `ApprovalMatrix` table: `(role, action_type, single_value_cap, daily_cap, requires_dual_auth_above, requires_owner_notify_above)`.
- Per-action `authorization_chain`: client UI gates the action; if over threshold, blocks until a second manager taps their PIN/biometric.
- "Manager swipe" UX: when a server triggers a void/comp, the *server's tablet* shows a "Awaiting manager" lock; manager taps & enters PIN. This is the industry pattern (Toast, Square, Lightspeed).
- Velocity anomaly detector: >N voids per server per hour → silent flag to GM, do not block.
- Per-shift comp budget visible to manager: "€87 / €150 used."

---

## 3. Audit Trail / Who-did-what

**Spec coverage:** Phase 5 mentions "Void Audit Trail" — a sortable ledger by Reason Code. That's a *report*, not an *audit log*.

**Gap:** No mention of an **immutable, append-only manager-action log** covering: voids, comps, discounts, price overrides, manual table moves, manual session re-opens, refund initiations, cash drops, schedule edits, menu price changes, role grants. No mention of WHO, WHEN, WHERE (device/IP), CONTEXT (table/session/customer), and the BEFORE/AFTER state snapshot.

**Concrete fixes:**
- Create `ManagerActionLog`: `id (ulid), actor_user_id, actor_role_at_time, action_type (enum), target_type+id, before_state (jsonb), after_state (jsonb), reason_code, free_text_note, customer_id_nullable, device_id, ip, occurred_at, session_id_at_venue`.
- **Append-only:** no UPDATE/DELETE grants on the table at the DB role level. Backups versioned.
- Sign each row with a daily HMAC chain (each row carries `prev_hash`) so tampering is detectable — this is also what fiscal regulators ask for.
- Include `customer_visible_explanation` separately from `internal_note` (because "Karen comped because guest was rude back" should NOT leak to the receipt).
- Surface log inside the manager UI: "Table 7 history" tab showing every intervention.

---

## 4. Shift Management

**Spec coverage:** Phase 1 mentions "Staff Load" as a KPI. That's it.

**Completely missing:**
- Clock-in / clock-out (with optional geofence or QR at host stand)
- Break tracking (paid vs unpaid, legally mandated break windows per jurisdiction — Switzerland Arbeitsgesetz Art. 15)
- Shift swap request → approval flow
- Open shift marketplace ("Pick up Saturday dinner")
- Tip pool: pool rules (by hours, by sales, by role weight), tip-out to back-of-house, transparency report
- Payroll export (CSV / API to Bexio, Abacus, ADP, Gusto)
- Overtime alerts: legal warnings before they happen, not after

**Concrete fixes:**
- Add `Shift`, `ShiftSegment` (clock-in/out events with reason on early leave), `Break`, `ShiftSwapRequest`, `TipPool`, `TipDistribution`.
- Manager dashboard: "Who is on the clock right now," "Approaching overtime," "Pending swap approvals."
- Payroll export: weekly batch + on-demand, with cost-center splits, in formats matching the local accounting tool (configurable adapter).
- Tip pool calculation engine runs at end-of-shift; produces a signed report each employee can view and dispute within 48h.
- Mobile clock-in for the staff (not just the manager).

---

## 5. Cash Handling / Tills

**Spec coverage:** Zero. Payment Phase 4 (client) only mentions Apple Pay / Google Pay / Card. No cash.

**Real-world reality:** In Switzerland/Germany/Austria cash is still 25-40% of restaurant payments. The system MUST handle:
- Cash payment posting against a check
- Server bank / float / starting drawer
- Drop boxes (cash deposited mid-shift to reduce till exposure)
- Blind cashout (server counts without seeing system-expected total → catches skimming)
- End-of-shift reconciliation: declared cash vs system-expected, with over/short logged and trended per server
- Safe transfer log, bank deposit log

**Concrete fixes:**
- Add `Till`, `TillSession`, `CashDrop`, `CashCount`, `CashOverShort` entities.
- "Cash" as a first-class `payment_method` on `Payment` with the same fiscal receipt requirements as card.
- Blind cashout flow: server enters counted amount; only after submission is the variance shown — to manager first, then server.
- Trend per server: average over/short, flag at >2σ.
- For owner: nightly safe drop report, weekly bank deposit reconciliation.

---

## 6. Inventory Tie-in

**Spec coverage:** Phase 4 mentions "Emergency Stock Toggles" → mark item "Sold Out" by one tap. That's a manual switch, not inventory.

**Gap:** No depletion engine, no recipe BOM (bill of materials), no 86-list, no purchase orders, no supplier integration, no waste tracking aggregation (despite the `is_wasted` boolean on voids — it goes nowhere).

**Concrete fixes:**
- `Ingredient` (with unit, cost, supplier, lead time, par level)
- `Recipe` linking `MenuItem` → list of `(Ingredient, quantity, unit, yield_factor)`
- On every served (BUMP) order item: decrement stock by recipe quantity in an outbox event → inventory service consumes it
- Auto-86 when projected stock < average sell-through to close
- Daily variance: theoretical use (from sales × recipes) vs actual count (from spot/full inventory)
- Waste log: `is_wasted` voids + manual waste entries → categorized weekly report
- Supplier ordering: minimum stock triggers PO suggestions, optionally auto-send to supplier via email/EDI
- Cost-of-goods-sold % KPI per category — this is the #1 number an owner asks for daily

---

## 7. Reservations No-show

**Spec coverage:** Client Phase 2 covers booking + cancel + modify. No deposit, no no-show fee, no late penalty, no overbooking policy.

**Real-world reality:**
- Fine dining and high-demand venues require a deposit or credit card hold (€30-50/cover typical in Europe)
- No-show fee policy must be presented at booking time (consumer law: explicit consent required)
- Late arrival > 15 min → table may be released; system should email/SMS the guest
- Walk-in waitlist with SMS/push when ready
- VIP / blacklist flags on customer records (e.g., chronic no-show)

**Concrete fixes:**
- `Reservation` gets: `deposit_amount`, `deposit_payment_intent_id`, `deposit_state` (held | captured | refunded | forfeited), `late_release_minutes`, `no_show_policy_text` (versioned, shown at booking and stored as accepted).
- Hold via Stripe SetupIntent (no charge unless rule fires).
- Manager UI: "Mark as no-show" → triggers capture of deposit; "Mark as late but seated" → no charge; "Comp the no-show fee" → uses the comp flow above.
- Customer profile flags: `vip`, `noshow_count`, `blacklist_reason`. Visible to host at booking attempt.
- Waitlist: walk-in queue with SMS notification, estimated wait, position tracking.

---

## 8. Multi-venue / Chains

**Spec coverage:** Singular "Restaurant" assumed throughout. No org/tenant/brand layer.

**Real-world reality:**
- A regional manager runs 3-5 venues. They need a "switch venue" dropdown that scopes ALL data — including KPI rollups across venues.
- An owner of a 12-location chain needs aggregated P&L, menu propagation ("push price change to all locations of brand X"), centralized HR with venue assignment, transfers (staff lent from venue A to B).
- Franchise model: master franchisor sees performance, can enforce brand standards (menu items, layout templates) without touching daily ops.

**Concrete fixes:**
- Introduce `Organization` → `Brand` → `Venue` (3-tier). Role grants are scoped to one of these tiers.
- "Switch context" in top bar; current scope shown persistently to prevent acting on wrong venue (a real source of catastrophic mistakes).
- Aggregated dashboard at Brand/Org tier: revenue, labor %, COGS %, ticket avg, all rolled up.
- Menu inheritance: brand-level menu template, venue-level overrides (price, availability) with audit on who-overrode-what.
- Staff `EmploymentAssignment` records linking a person to one or more venues with per-venue role.

---

## 9. Reporting / Exports

**Spec coverage:** Phase 5 says "Shift Reporting: comprehensive exports comparing order injection to BUMP times." That's *prep performance only*. Missing the entire finance/operations report suite.

**Concrete fixes — add these reports as first-class features:**
- **Daily Z-Report** (end-of-day fiscal close): gross sales, by tax rate, by category, by tender, voids, comps, discounts, employee meals, no-show fees, with fiscal signature.
- **Daily X-Report** (mid-day snapshot, non-fiscal).
- **Weekly/Monthly P&L hooks**: feed revenue, COGS (from inventory), labor (from shifts) into a P&L schema.
- **Accounting export adapters**: Xero, QuickBooks Online, Sage, Bexio (CH), Abacus (CH), DATEV (DE), SAP Business One. CSV + API.
- **VAT report**: per VAT rate, with the takeaway-vs-eat-in split (CH/DE require different rates), exportable to the tax filing format.
- **Waste log export** (linked to inventory engine).
- **Tip/payroll export**.
- **Customer/marketing exports** (compliant with GDPR consent flags).
- All reports: scheduled email/SFTP delivery, retention 7 years (fiscal requirement in EU).

---

## 10. Compliance / Data

**Spec coverage:** None. No GDPR, no PCI, no allergen, no food safety mention.

**Real-world legal floor — not optional:**

**GDPR:**
- Right to access (DSAR): manager (or DPO) must be able to export every record about a named guest within 30 days.
- Right to erasure: must be able to anonymize a guest while preserving the fiscal records (which by tax law must be retained 7-10 years — the bill keeps existing without the name).
- Data retention policy per data class: marketing opt-in (until withdrawn), reservation history (24 months default), fiscal (10y), CCTV/video (none in spec but if added: 7 days).
- Consent log: explicit consent for marketing, separately for analytics cookies.

**PCI-DSS:**
- The spec says "without passing raw CC data to the TableMate backend" (good — SAQ-A scope).
- BUT: ensure no PAN ever traverses logs, error reports, support screenshots, WebSocket payloads.
- Vendor attestation chain: Stripe AOC needs to be on file; TableMate AOC must be produced annually.
- BIN/last4 stored only via the payment provider's tokens.

**Food safety / allergens:**
- EU Reg 1169/2011: 14 mandatory allergens must be disclosable per dish, in writing.
- Each `MenuItem` needs `allergens[]`, `may_contain[]`, `nutritional_info`, `last_updated_at`, `responsible_staff_id`.
- HACCP integration optional but expected: temperature logs, fridge checks, cleaning schedules.

**Concrete fixes:**
- `Customer.privacy_state`: `active | anonymization_requested | anonymized`. Anonymization sets PII fields to NULL/hash but preserves linked transactions.
- Manager UI: "Privacy" section per customer with export-as-JSON and erase buttons (latter behind owner + DPO co-approval).
- Allergen schema on `MenuItem`; client app surfaces, waiter UI surfaces during order taking, kitchen ticket surfaces with bold "ALLERGY: NUTS" header when guest profile has an allergy flag.
- Consent log: every checkbox a customer ever ticked, with timestamp and IP, immutable.

---

## 11. Staff Training Mode / Sandbox

**Spec coverage:** None.

**Real-world need:** New servers spend 1-2 shifts learning the POS. You can't have them practicing on live orders that hit the kitchen.

**Concrete fixes:**
- `TrainingMode` per user session: orders are flagged `is_training = true`; they do NOT inject into kitchen Kanban, do NOT fire WebSocket events to the real cooks, do NOT create financial records.
- Optional: a parallel "training kitchen" view a manager can monitor to grade the trainee.
- Demo data preloaded (sample tables, sample menu, sample guests).
- Visible "TRAINING" watermark on every screen so a returning live shift can't be confused.

---

## 12. Role Separation Manager vs Owner

**Spec coverage:** Lumped as "Admin" with one role.

**Real-world reality:**
- **Manager (operations):** sees today's revenue, void/comp activity, staff on shift, menu 86s, table moves, customer complaints. CANNOT see: their own salary, owner's profit, supplier invoices, payroll for others, P&L, accountant exports.
- **Owner / GM (financial):** sees P&L, payroll, supplier costs, lease/utilities, owner draws, multi-venue rollups, accounting exports, tax filings.

**Concrete fixes:**
- Split into at minimum: `Cook`, `Waiter`, `Host`, `ShiftManager`, `GeneralManager`, `Owner`, `Accountant`, `Auditor` (read-only fiscal).
- Permissions matrix: each report, each setting page, each action gated per role.
- "Sensitive financials" flag on screens so a shift manager glancing over an owner's shoulder doesn't accidentally see the margin.

---

## 13. Override Locks

**Spec coverage:** Phase 3 says "Publish Layout" pushes via WebSockets. No concurrency control mentioned.

**Real-world reality:** Two managers in two browser tabs editing the floor plan at the same time → last write wins → one manager's work silently discarded.

**Concrete fixes:**
- Pessimistic lock on `FloorPlan.edit_session`: when manager A enters Edit Mode, lock acquired (5-minute TTL, refreshed on activity). Manager B sees "Currently being edited by Karen since 14:32 — request takeover?"
- Optimistic alternative: each save includes `expected_version`; conflict → diff UI showing both changes for manual merge.
- Same pattern for: menu editing, price changes, schedule editing.
- Audit `lock_taken / lock_released / lock_force_taken` events.
- Soft-conflicts on per-table fields: granular row locking instead of whole-plan if performance matters.

---

## 14. Customer Complaint Resolution

**Spec coverage:** Client Phase 3 mentions "leave reviews" in the History tab. No routing to manager.

**Real-world need:** A 1-star review left while the guest is still on premise (or within 30 min) is a recoverable situation. After that it goes public and the venue loses standing.

**Concrete fixes:**
- Negative review threshold (≤ 3 stars) within the venue or within X hours of session close → high-priority push to manager on duty with full session context (table, server, items, total, void/comp history).
- Manager UI: "Open complaints" inbox with SLA timer (e.g., respond within 60 min).
- Reply path: manager can comp/refund/offer-voucher directly from the complaint card.
- Aggregate signal: 3+ negative reviews for the same dish in a week → flag to chef.
- Optional: hold publication of public reviews for 1-hour cooling-off window during which manager can engage.
- Linked to the comp/discount engine above so service recovery is tracked and not just gifted off-the-books.

---

## Top 10 Admin/Manager Improvements (Prioritized)

| # | Improvement | Priority | Why now |
|---|-------------|----------|---------|
| 1 | **Comp/Discount/Void split** with proper tax-aware lifecycle and approval matrix | **H** | Without this, fiscal certification fails in CH/DE/AT/IT/FR and managers fall back to off-system workarounds (fraud risk). |
| 2 | **Immutable Manager Action Log** (hash-chained, append-only) | **H** | Required for fiscal regulators and for any insurance/labor dispute. Foundation for trust. |
| 3 | **Cash handling + till reconciliation** (incl. blind cashout) | **H** | 25-40% of EU restaurant revenue. Without it, the product is unusable for any cash-accepting venue. |
| 4 | **Shift lifecycle** (clock-in, breaks, swaps, tips, payroll export) | **H** | Manager's #1 daily task after service. Drives labor cost — the second-biggest P&L line. |
| 5 | **Inventory engine with recipe BOM, depletion, waste, COGS%** | **H** | The `is_wasted` flag is meaningless without it. Owners demand COGS daily. |
| 6 | **Fiscal reporting suite** (Z/X reports, VAT, accounting exports, retention) | **H** | Legal floor in EU. Without it, customers literally cannot file taxes from the system. |
| 7 | **GDPR + allergen compliance** (DSAR, anonymization, allergen schema, consent log) | **H** | EU Reg 1169/2011 + GDPR — operating without them risks 4% global-turnover fines and food-safety liability. |
| 8 | **Role split: Manager / GM / Owner / Accountant / Auditor** + approval thresholds | **M** | Operational hygiene. Prevents accidental data exposure and unblocks delegation. |
| 9 | **Multi-venue context with org/brand/venue hierarchy and rollups** | **M** | Unlocks the chain/franchise market. Without it, revenue cap is one venue per account. |
| 10 | **Reservation deposits + no-show fee flow + customer flags (VIP/blacklist)** | **M** | Recovers lost revenue, deters chronic abusers, parity with OpenTable/SevenRooms baseline. |

*Items below the cut but worth noting: training/sandbox mode (M, blocks onboarding velocity), customer complaint routing (M, brand protection), spatial-edit locking (L, low frequency but high embarrassment when it bites), HACCP food-safety logs (L, jurisdiction-dependent).*

---

## Closing observation

The spec reads like it was written by someone who watched a busy service through a window. The real-time UI is good. But a manager's job during service is **40% recovery (voids/comps/complaints), 30% money (cash, fiscal, tips), 20% people (clock-in, breaks, coverage), and 10% editing the floor plan.** The spec currently optimizes for the 10%. To ship a product real managers will adopt and not work around, the 90% must come in before launch — or at least before the second pilot venue.
