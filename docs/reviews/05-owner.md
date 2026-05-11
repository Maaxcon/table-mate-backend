# TableMate — Restaurant Owner Review

**Reviewer hat:** Owner of one or several venues. Lens: ROI, margin, growth, risk, lock-in.
**Source reviewed:** `/Users/oleksandrstepanenko/unibrix/ table-mate/table-mate-backend/docs/architecture-and-workflows.md`

> Headline: The spec is essentially a **floor-plan + KDS + prepaid-QR-ordering MVP**. As an owner, I cannot make a buy decision on this document. It tells me how a ticket moves from QR scan to kitchen BUMP, but it does not tell me how it makes me more money than my existing POS, what it costs me to run, or what I lose if I leave.

---

## 1. Revenue lift hypothesis — WEAK / mostly buzzword

**What the spec actually delivers toward revenue lift:**
- Faster turnover: *partially.* Atomic dish-ready signals, Time-at-Table ring, bottleneck heatmaps — yes, these can shave minutes off table cycle. Real, but unquantified.
- Fewer voids: *partially.* Voids are logged with reason codes and audit trail; that helps me train, but it does not prevent the void.
- Prepaid client orders: *yes, real.* No "dine-and-dash," no order taken wrong, payment cleared before fire — that is a genuine lever (lower comps/walkouts, faster card settlement).
- Tip retention: **NOT IN SPEC.** No mention of tipping at all, anywhere. Massive miss for a restaurant tool.

**What is missing entirely:**
- **No upsell engine.** Client menu has no "frequently bought with," no "make it a combo," no suggested wine pairing, no "add a dessert before checkout." The single most repeatable revenue lever in restaurant tech is absent.
- **No cross-sell prompts** on the waiter side either ("Table 4 hasn't ordered drinks in 15 min — prompt?"). Nothing.
- **No happy-hour / dynamic pricing / time-banded menus.** "Sold Out" toggle is the only menu lever — purely defensive.
- **No loyalty program logic** (see §4).
- **No repeat-visit driver.** History tab is read-only. No "we miss you, here's 10% off this week."
- **No bill-splitting / pay-by-seat at checkout.** "Items pre-organized by guest seat" is mentioned for waiter view but not for client payment — splitting a check increases tip frequency and removes a friction point.

**Concrete fixes:**
- Add a `Recommendation` service: rule-based first (item co-occurrence, margin-weighted), ML later. Inject into Client checkout and Waiter "add item" flow.
- Add `MenuSchedule` (dayparts, happy hour, weekend pricing) on `MenuItem`.
- Add explicit **tip capture step** in payment flow with configurable suggested % and round-up.
- Add `SplitBill` in Order: even split, by-seat, custom.

---

## 2. Cost of ownership — NOT ADDRESSED

**Gap:** Spec is silent on what the owner actually pays / buys / trains.
- How many tablets? Per waiter, per section, per host stand? BYOD allowed?
- KDS hardware: dedicated screens, iPad, Android? Wall-mount? Bump bar peripheral?
- Receipt printer: needed at all? ESC/POS-compatible? Cash drawer trigger?
- Payment fees: passed to Stripe — what is the effective rate I see vs. my current acquirer? Surcharge rules legal in my jurisdiction?
- Connectivity: assumed always-on (see §13). What is the bandwidth floor?
- Training time: spec UX is dense (modifiers, guest slots, batch view, bump). No "training mode" mentioned.
- Support SLA: zero mention.

**Concrete fix:**
- Add an **"Operating Requirements & TCO" section** to the doc: hardware BOM tiers (Starter / Pro / Multi-venue), connectivity SLOs, supported peripherals matrix (printers, KDS, payment terminals), onboarding hours estimate, support tiers (email / chat / phone / on-call), and effective payment cost worked example.

---

## 3. Lock-in / migration — WEAK

**What's there:** Immutable financials (good for audit), versioned floor plan layouts (nice).

**What's missing:**
- **No data export.** I cannot find one mention of CSV/JSON/Parquet export for: menu, orders, sessions, customers, reviews, voids, payouts. "Shift Reporting — Comprehensive exports" is mentioned but undefined.
- **No menu import.** Onboarding a 200-item menu by hand is a non-starter.
- **No customer data ownership clarity.** If a guest signs in with Google OAuth at my venue, is that customer mine, TableMate's, or shared? Critical for marketing and GDPR.
- **No portability API** for moving to another POS later.

**Concrete fix:**
- Define **Data Ownership clause** in spec: owner owns menu, orders, customer records collected at their venue.
- Ship a `GET /export/{entity}.csv` and a one-click "Full account export" (GDPR Art. 20 portability anyway).
- Menu import: CSV + a Square/Toast/Lightspeed mapper.

---

## 4. Marketing & loyalty — BUZZWORD ONLY

**What's there:** The Personal Cabinet header says "Identity & Loyalty" and then defines nothing more than "Member since 2024." That is **not loyalty**, that is a join date.

**What's missing:**
- No points, no tiers, no stamp card, no referral, no birthday reward, no win-back, no first-visit incentive.
- No SMS / email / push marketing engine.
- No segments ("guests who haven't been back in 45 days," "spent > €200 lifetime").
- No campaign tooling.
- No reservation reminders / waitlist follow-up.

**Concrete fix:**
- Add a `Loyalty` module: configurable accrual rule (e.g., 1pt per €1), redemption ladder, optional tiers, birthday auto-credit.
- Add a `Marketing` module: segments, transactional + promotional templates, send via SendGrid/Twilio, double opt-in for GDPR.
- Add waitlist + reminder SMS at booking.

---

## 5. Reviews & reputation — INTERNAL-ONLY (LOSES VALUE)

**What's there:** "Users can tap to view itemized electronic receipts or leave reviews." Reviews live inside the Client cabinet. No public surface for them.

**What's missing:**
- No syndication to Google / Yelp / TripAdvisor / TheFork.
- No review-request prompt timing (post-visit, 2-hour window).
- No private-first routing (low-rating → goes to manager, not public).
- No reply-to-review tool for the owner.

**Concrete fix:**
- Trigger a post-visit review prompt 60–120 min after `Session.closed`.
- Branch on rating: 4–5 stars → deep-link to Google review; 1–3 stars → internal feedback ticket routed to manager.
- Owner-facing "Reviews" tab with reply, flag, and trend chart.

---

## 6. Multi-location P&L — ABSENT

**Gap:** Entire spec is single-venue. `Restaurant` is in the schema, but there is no concept of:
- A `Brand` or `Group` entity that owns multiple restaurants.
- Cross-venue revenue aggregation, P&L comparison, league tables.
- Waiter performance across venues (a roving manager can't compare).
- Central menu with per-venue overrides (price, availability, tax).
- Centralised staff (one login works at 3 venues with venue-scoped roles).

**Concrete fix:**
- Introduce `Organization` → `Venue` hierarchy. `Staff` has many `VenueMembership` rows with role-per-venue.
- Central menu inheritance: `MenuTemplate` at Org level, `MenuOverride` at Venue level.
- Multi-venue dashboard: revenue, prep time, void rate, table turn per venue, side-by-side.

---

## 7. Payroll & tips — COMPLETELY ABSENT

**Gap:** The word "tip" does not appear in the document. For a restaurant platform this is shocking.

**What's missing:**
- Tip capture at checkout (% suggestions, custom, round-up).
- Service charge config (auto-gratuity on 6+, banquets).
- Tip pool rules (pooled vs. retained, by role weight, by hours).
- Cash-tip declaration.
- Payroll export (hours from clock-in, tips, by employee).
- Clock-in / clock-out / shifts (no time-clock feature at all).

**Concrete fix:**
- Add `Tip` and `ServiceCharge` to Order. Configurable per venue.
- Add a `TipPool` engine with rule sets (e.g., 70% server, 20% bar, 10% bussers).
- Add `Timesheet` (clock-in/out) and a CSV payroll export plus integrations to Deputy / 7shifts (§8).

---

## 8. Integrations — SILENT

**Gap:** Zero third-party integrations named. For an owner this is the #1 sticky question.

**What's missing (representative):**
- **Accounting:** Xero, QuickBooks, Sage (daily journal export).
- **HR / scheduling:** Deputy, 7shifts, Sling.
- **Delivery:** Uber Eats, Deliveroo, JustEat, DoorDash (menu sync, order ingest into KDS).
- **Inventory:** MarketMan, Apicbase, MarketBoy (deduct from `is_wasted` void + sale).
- **Reservations:** OpenTable, TheFork, Google Reserve, Resy.
- **Marketing:** Mailchimp, Klaviyo, SendGrid.
- **BI:** Looker, Metabase, Power BI (read-only warehouse view or Fivetran connector).
- **Identity:** Apple Sign-In (Google OAuth only is a non-starter on iOS App Store).

**Concrete fix:**
- Publish an **Integration Roadmap** with named partners and tiers (Day 1, Quarter 2, Quarter 4).
- Stand up a stable **public REST + webhook API** with OAuth2 client credentials so partners can self-integrate.
- Add a "Marketplace" UI in Admin to enable/disable integrations.

---

## 9. Compliance & risk — PARTIAL

**What's there:** Stripe tokenisation keeps raw CC off the backend (good, PCI scope minimised). Immutable financial records (good for tax audit).

**What's missing:**
- **GDPR:** No mention of right-to-erasure for customers, no data export to fulfil portability, no privacy policy hooks, no cookie consent, no data residency (EU vs US).
- **Allergens / food safety:** Menu has no allergen fields, no HACCP, no "may contain" disclosure. EU Regulation 1169/2011 mandates this. Liability risk.
- **Tax:** No VAT rates per item, no per-region tax (a UK 20% standard + 0% takeaway split), no inclusive vs exclusive pricing toggle, no tax invoice format compliance (Italy SDI, Germany TSE/KassenSichV, France NF525, Spain TicketBAI — any of these are blockers in those markets).
- **Tipping law:** US tip credit, UK Allocation of Tips Act 2024 (mandatory written policy + fair distribution within a month), EU service-charge VAT rules — none addressed.
- **Age verification:** Alcohol items in menu — no 18+/21+ gate.
- **Accessibility:** WCAG 2.1 AA not mentioned; Client app is a public-facing surface and falls under EAA from June 2025.

**Concrete fix:**
- Add `Allergen[]` and `NutritionInfo` on `MenuItem` (mandatory in EU).
- Add `TaxRate` table, per-venue, per-item-category, with region presets.
- Add a Compliance section to the spec covering GDPR DSR endpoints, fiscal compliance per market, tip-law policy storage, age-gate, WCAG.

---

## 10. Brand customization / white-label — ABSENT

**Gap:** Client app is described generically. No theming.

**What's missing:**
- Logo, colour palette, font, hero imagery per venue.
- Custom domain (`order.mybistro.com`).
- Multi-brand under one owner (group with 3 distinct concepts).
- White-label of the Client PWA / native shell.

**Concrete fix:**
- `BrandTheme` per Venue / Brand. CSS variables exposed.
- Custom-domain pipeline (CNAME + auto-TLS via Let's Encrypt).
- Optional native white-label app under owner's developer account (heavy lift — flag as Pro tier).

---

## 11. Pricing model risk — UNKNOWN

**Gap:** The spec is purely technical; it never tells me what TableMate charges me.

**What I need to know to evaluate ROI:**
- Flat SaaS fee per venue / per terminal / per cover?
- % of transaction on top of Stripe?
- Tiered features (loyalty / multi-venue gated behind upper tiers)?
- Payment-processing margin: am I forced onto TableMate's Stripe account or can I bring my own?
- Contract length, exit clause, price-rise cap.

**Concrete fix:**
- Add a separate **Commercial Model** doc (even internal): pricing tiers, what's in each, BYO-Stripe yes/no, exit clauses. Without this no owner signs.

---

## 12. Insurance & dispute — WEAK

**What's there:** Void audit log, immutable session snapshot.

**What's missing:**
- **Chargeback evidence pack:** when Visa/Mastercard disputes a card, I need a one-click bundle (order log, items served, timestamps, server name, IP, device fingerprint, signed receipt). Not in spec.
- **Customer "didn't get my food" claim flow:** no formal dispute path in the Client cabinet.
- **Refund flow:** voids are described as in-session corrections. What about a refund 3 days later? Partial refund? Refund-to-original-payment-method audit?
- **Liability boundary:** if the system loses an order, who eats the cost?

**Concrete fix:**
- Add a `Dispute` entity with state machine (opened → evidence-gathered → submitted → resolved). One-click Stripe Dispute API submission with bundled evidence.
- Add post-visit Refund flow in Admin with reason code, partial-amount, audit log.

---

## 13. Hardware / redundancy — RISKY

**What's there:** "Disconnected — destructive actions disabled." That is honest, but it is also brutal at 8pm Saturday.

**What's missing:**
- **Offline POS mode.** When WiFi drops, waiters need to still take orders, queue them locally, and reconcile on reconnect. Spec hard-disables writes — this is wrong for restaurants.
- **Local KDS cache** so the kitchen can finish tickets even if the cloud is unreachable.
- **Receipt printer fallback** if the screen dies.
- **Tablet failure plan** — hot spare? Re-login on a different device with the same session?
- **Payment terminal offline mode** (Stripe Terminal supports it; spec doesn't mention).

**Concrete fix:**
- Define an **Offline-First** mode: local queue with conflict-free merge on reconnect (CRDT or last-write-wins per item plus manual review queue).
- Local mDNS fallback channel between waiter and KDS on the venue LAN — so they keep talking even if WAN is down.
- Hardware HA: spare tablet flow, printer kick fallback.

---

## 14. Disaster recovery — NOT ADDRESSED

**Gap:** No RTO, no RPO, no backup cadence, no incident playbook, no status page mention, no paper-fallback procedure.

**Concrete fix:**
- Publish an SLA: uptime target, RTO < 1h, RPO < 5 min, automated DB backups + PITR.
- Status page (status.tablemate.app) with WebSocket-broadcast incidents into the admin UI.
- "Paper Mode" runbook: print-from-Admin daily snapshot of bookings + menu + prices so the venue can run on paper if the system is fully down.

---

## TOP 10 OWNER-FACING IMPROVEMENTS

Priority H = blocking purchase decision, M = strong differentiator, L = nice-to-have.

| # | Improvement | Priority | Business value (1 line) |
|---|---|---|---|
| 1 | **Add tipping, service charge, and tip-pool engine + payroll export** | **H** | Without tips, this is not a restaurant product — and tip retention/transparency is a top staff-retention and revenue driver. |
| 2 | **Add Offline-First mode for waiter, KDS, and payments** | **H** | One WiFi outage on a Saturday night without a fallback costs more than a year of subscription — and is the #1 question every owner asks before signing. |
| 3 | **Add Multi-Venue (Organization → Venue) with central menu and cross-venue analytics** | **H** | Unlocks the 3+ venue segment, which is where SaaS LTV actually compounds; without it the product caps at single-shop. |
| 4 | **Define data ownership + full data export (menu, orders, customers, reviews)** | **H** | Removes the #1 procurement blocker ("what happens if I leave?") and satisfies GDPR portability for free. |
| 5 | **Ship a real loyalty + marketing engine (points, segments, win-back email/SMS, birthday)** | **H** | Repeat visits are 5–10x cheaper than acquiring a new diner; the spec currently has the word "Loyalty" but zero mechanism behind it. |
| 6 | **Add menu allergens, per-item tax rates, and market-specific fiscal compliance (UK/EU/US)** | **H** | Without these the platform cannot legally operate in EU markets, full stop. |
| 7 | **Add upsell / cross-sell engine in Client checkout and Waiter add-item flow** | **M** | Even a 3% AOV lift on a €60 cover at 1,000 covers/week = ~€90k/year of margin — the cleanest ROI lever in the stack. |
| 8 | **Integrations roadmap with named partners: Xero/QuickBooks, Deputy/7shifts, Uber Eats/Deliveroo, OpenTable, Mailchimp** | **M** | Owners do not rip-and-replace 6 systems; they buy whatever plugs into the 6 they already have. Silence here = silent rejection. |
| 9 | **Public-review syndication (Google/TripAdvisor) with private-first low-rating routing** | **M** | Converts each happy visit into a public marketing asset and keeps the unhappy ones out of public view — direct effect on top-of-funnel. |
| 10 | **Brand theming + custom domain for the Client app** | **L** | Lets the owner present TableMate as their own product, not "yet another aggregator," protecting brand equity and conversion. |

---

## Owner verdict in one paragraph

Operationally this is a competent **kitchen-flow + QR-ordering MVP** with a good real-time backbone and clean separation of voids, sessions, and immutable financials. As a **business product** it is missing every layer that determines whether a restaurant actually earns more or pays less — no tips, no loyalty, no marketing, no allergens/tax/legal, no multi-venue, no integrations, no offline mode, no exit ramp. I would not switch from my current POS on the basis of this document. I would, however, evaluate it as a **front-of-house add-on** to an existing POS once items 1–6 above are filled in.
