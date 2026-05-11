# TableMate — Client-Side Spec Review (Diner Hat)

Reviewed against `docs/architecture-and-workflows.md`, Part 1 plus any client-touching surfaces in Parts 2–4. The spec is competent on the **happy path of a logged-in solo diner who pays in advance** and falls apart almost everywhere else. Below: ten realistic diner scenarios, then a prioritized fix list.

---

## Scenario 1 — Walk-in solo diner, 7pm Friday, told "table in 20 min"

- **What breaks:** Phase 1 only models two entry modes — (A) in-venue QR or (B) remote catalog. There is no "I am standing at the host stand, not seated yet" mode. A "Free" table that is *physically empty but reserved for me in 20 min* has no representation: the legend only has Free / Occupied / Reserved (someone else). No waitlist, no SMS-when-ready, no virtual queue position, no "join party" handoff at seating.
- **User emotion:** Awkward limbo. Stands in entryway holding phone, doesn't know whether to scan a QR (which one?), can't browse menu meaningfully because Scenario B blocks live ordering, can't pre-order to save 20 min.
- **Missing feature:** Walk-in waitlist with virtual queue, SMS/push "your table is ready", and a *Pre-Seat Menu* mode that lets a confirmed-walk-in browse and stage an order without firing it. Also a host-issued short code / NFC at the door to bind the guest to the pending seat before the QR exists.

---

## Scenario 2 — Group of 6, birthday, mixed diets, one person remote

- **What breaks:** Booking in Phase 2 captures only Table / Date / Time / Guest Count. There is no party model — no invitee list, no shareable join link, no per-guest dietary metadata, no remote add-on (e.g. cousin on Zoom contributing to the cake order). Phase 4 Checkout is single-payer-on-one-device; the "items pre-organized by guest seat" in Waiter Phase 3 implies guest slots exist, but the spec never explains *how the client app creates them* before the waiter touches the table. The remote person from Scenario B has *live ordering blocked*, so they cannot contribute at all.
- **User emotion:** Host is herding cats over WhatsApp ("text me your order"), retyping it into one phone. Remote guest feels excluded. Birthday person sees no cake/candles flow.
- **Missing feature:** Group/party object with shareable invite (deep link + magic code), per-guest sub-carts that merge at checkout, remote-guest "browse & add" that lifts the Scenario B block once the host has confirmed the booking, dietary tags on guest profile, special-occasion field (birthday/anniversary) that surfaces to waiter.

---

## Scenario 3 — Family with kids, allergies, high chair, split parent cards

- **What breaks:** No kids' menu surface, no high-chair / stroller-space request on the booking modal (Phase 2 captures none of that). No allergy profile on the Personal Cabinet (Phase 3 lists name + registration date + payment methods, period). The "Checkout Rule" in Phase 4 explicitly forbids the non-online-pay fallback — fine — but only describes Apple/Google/Card as a single payment, no split. Allergies cannot be attached to an order item; the only free-text channel is the waiter-side Modifier Modal ("No onions"), which the *client* never sees.
- **User emotion:** Parental anxiety. "Did the kitchen actually see the peanut allergy?" Parents argue over who Apple-Pays.
- **Missing feature:** Kids-menu category + age-appropriate portion flag; booking add-ons (high chair, booster, stroller, wheelchair) as structured fields; allergy/diet profile on user account that auto-attaches to every order and is *visible to kitchen* with hard-block on conflicting ingredients; split-bill UI (by item, by share, by guest slot) with multiple payment intents.

---

## Scenario 4 — Business dinner, separate company card, itemized VAT receipt

- **What breaks:** Phase 3 history shows "12 OCT 2024 — €142.00" and lets you "tap to view itemized electronic receipts" — but nothing about VAT number on the receipt, company billing details, expense-app forwarding (Expensify, SAP Concur, Pleo, Rydoo), or *separating one guest's items onto a different payment method on the same session*. Phase 4 is single-payer.
- **User emotion:** Awkward at table ("can you put mine on a separate card?"), then frustration two weeks later when finance rejects the receipt for missing VAT ID.
- **Missing feature:** Business profile (company name, VAT ID, billing email) attachable per-transaction; PDF/eReceipt with full fiscal fields; one-tap forward to email/expense integrations; split payment with per-payer receipts.

---

## Scenario 5 — Tourist, non-English, wants Apple Sign-In or email magic link

- **What breaks:** Phase 1 Authentication: *"Logging in redirects to Google OAuth"* — that's the only option besides Guest. No Apple Sign-In (a hard App Store requirement if Google is offered), no email/magic-link, no phone OTP. Profile settings vaguely mention "language" but the menu, modifier modal, kitchen comments, and notifications have no i18n contract anywhere in the doc. Currency formatting (€) is hard-coded in examples. No translated allergen names.
- **User emotion:** Tourist abandons in 30 seconds — can't read menu, can't sign in, falls back to flagging a human waiter (but Phase 4 explicitly removed the "Call Waiter to Order" fallback).
- **Missing feature:** Apple Sign-In + email magic link + phone OTP; full i18n with detected device locale; menu translations + allergen icons (EU-14 standard); currency/locale formatting; menu photos with captions; pictogram-only ordering mode.

---

## Scenario 6 — Repeat regular, wants "the usual," remembered allergies

- **What breaks:** Phase 3 Profile has History but no "Favorites," no "Reorder last," no "My usual," no loyalty/points, no allergy memory, no waiter-side surfacing of regular status. "Member since 2024" is decorative. The Admin Phase 5 analytics treat the diner as a row in a heatmap, not a person with continuity.
- **User emotion:** "They never remember me." Mild churn risk; nothing pulls them back vs. a competitor with a punch card.
- **Missing feature:** Favorites list, one-tap reorder from History, saved diet/allergy profile that pre-filters menu, loyalty tier with visible perks, optional "notify my regular waiter" flag, birthday remembered.

---

## Scenario 7 — Cancellation 30 min before, prepaid

- **What breaks:** Phase 2 says canceled reservations are "gracefully archived… with a distinct 'Canceled' badge." Beautiful — but it never says what happens to the *prepaid order* (Phase 4 already pushed money + fired the ticket to Kitchen Kanban on payment). Does the kitchen get a Void event? Who triggers it — client cancel or admin Phase 2 Void flow? Is the money refunded fully, partially, or held? There's no cancellation-window policy (e.g. >2h = full refund, <30min = forfeit) and no refund state on the order.
- **User emotion:** Panic — "did I just pay for food no one will eat, and is the chef plating my steak right now?" Distrust if charged with no clear policy.
- **Missing feature:** Cancellation policy engine with windows + partial-refund rules; client-initiated cancel that fires a Void event to KDS (re-using Feature 7 atomic transaction); refund state machine on Order; in-app refund receipt.

---

## Scenario 8 — Modification after submission (add a side after kitchen fired)

- **What breaks:** The doc has no "amend order" flow on the client side at all. Once Phase 4 fires payment, the ticket lives in the kitchen Kanban; the only ways to change it are admin Void (Part 4 Phase 2) or — implicitly — waiter-led add-on (Part 2 Phase 4), which means flagging down a human. The "Call Waiter to Order" fallback is explicitly removed, so the client has *no* in-app path to add a side after submission.
- **User emotion:** "I literally cannot give you more money." Annoyed, then resorts to physical waving.
- **Missing feature:** Add-to-order flow that creates a *child ticket* injected at current timestamp into Incoming; clear UI showing locked items (already cooking) vs. open items (still modifiable); per-item cancellation window (e.g. drinks always modifiable, mains lock at "Yellow/InProgress").

---

## Scenario 9 — No-show

- **What breaks:** The spec has no concept of arrival confirmation, grace period, auto-release of held tables, no-show penalty, or deposit forfeit. A reserved table that nobody scans into is stuck in Reserved status indefinitely from the waiter's POV (Part 2 Phase 1 shows "guest name and expected arrival time" but no auto-expiry). The diner faces no consequence — encouraging hoarding.
- **User emotion:** From the *honest* diner's side, anxiety on the way ("am I late enough to lose the table?"); from the *no-show* side, indifference because there's no card hold or penalty.
- **Missing feature:** Reservation deposit / card hold for prime slots; grace period + auto-release after N minutes; check-in via QR at table within window; configurable no-show fee; trust score on user profile.

---

## Scenario 10 — Accessibility (wheelchair, screen reader, hard-of-hearing)

- **What breaks:** Zero accessibility content in the doc. The booking UI is described as a "spatial floor plan" with color-coded statuses — color is the *only* status channel mentioned (Free/White, Occupied/Solid, Reserved/Gray), which is a WCAG fail. No mention of accessible-table tagging in Phase 2, no ARIA/semantic guidance in Feature 9 (Live Floor Plan Engine), no captioning for the "audio cancellation chime" in Feature 7, no haptic alternative to the "pulse" alerts (Phase 5 dish-level monitoring), no large-text/high-contrast mode beyond a vague "dark mode" mention. Wheelchair routes, step-free entrance, accessible WC are not booking attributes.
- **User emotion:** Wheelchair user can't tell which tables fit them, calls the restaurant. Screen-reader user gets a floor plan canvas with no labels. Hard-of-hearing user misses the chime that signals their void.
- **Missing feature:** WCAG 2.2 AA compliance pass; accessibility tags on tables (step-free, wheelchair clearance, low-light avoid, near-restroom); non-color status redundancy (icons + labels); screen-reader-friendly table list as alternative to spatial map; haptic + visual fallbacks for every audio cue; adjustable text size and high-contrast mode.

---

## Cross-cutting gaps the spec is silent on

- **Tipping**: never mentioned. Service-included or not? Tip on card?
- **GDPR / data rights**: no export, no delete-my-account, no data-retention policy, no marketing-consent toggle. EU restaurant SaaS — non-negotiable.
- **Reviews**: Phase 3 mentions "leave reviews" once; no rate-limiting, no anti-abuse, no per-dish vs. per-visit distinction, no waiter rating.
- **Offline / poor connectivity**: Feature 12 hard-disables write actions on disconnect — fine for staff, *brutal* for a diner mid-checkout. No offline-tolerant cart, no retry queue.
- **Push notifications & comms channel**: assumed but undefined (web push? email? SMS?). No "your order is ready" to client — only to waiter.
- **Menu UX**: no dietary filter (vegan, GF, halal, kosher), no calorie/macros, no allergen icons, no spice level, no portion size, no "popular" / "chef's pick", no photos requirement, no search.
- **Table sharing on one device**: a host wanting to pass the phone around to let each guest pick. No "share menu via QR-to-QR" between two phones at the same table.
- **Guest checkout**: Phase 1 offers "Continue as Guest" but Phase 3 (the cabinet) and Phase 4 (saved payment methods, history, receipts) implicitly require an account. The guest's lifecycle dead-ends.
- **Receipt delivery**: spec implies in-app only; no email/SMS receipt, no print-at-table, no QR-to-download.
- **Currency, tax, service charge breakdown** on the receipt: undefined.
- **Pre-order arrival time**: Scenario B blocks live food orders entirely. There's no middle ground of "order ahead, fire when I sit down."

---

## Top improvements (prioritized)

| # | Improvement | Priority | Where it lands |
|---|---|---|---|
| 1 | **Allergy & dietary profile on user account, propagated to every order and hard-blocking conflicting items** — new section in Phase 3 Personal Cabinet ("Dietary Profile" card with: allergens multi-select, diet preset vegan/GF/halal/kosher, free-text note), surfaced to kitchen ticket header and waiter Phase 3 review. Hard validation: ordering an item flagged with a listed allergen requires explicit override modal. | **H** | Phase 3 Profile; Feature 5 Modifier Modal; Kitchen Phase 1 Incoming ticket header |
| 2 | **Split-bill + multi-payer checkout** — Phase 4 Checkout screen becomes a multi-intent flow: "Pay all / Split equally / Split by item / Split by guest slot." Each payer gets their own Apple/Google/Card sheet and their own receipt. Receipts include VAT ID & business billing fields if a Business Profile is selected. | **H** | Phase 4 Checkout; new "Business Profile" card in Phase 3 |
| 3 | **Apple Sign-In + email magic link + phone OTP, plus full i18n** — Phase 1 Authentication screen gets three additional providers; locale auto-detected from device, with explicit language switcher in greeting screen. All menu items, modifier labels, allergens, and notifications run through translation layer. Apple Sign-In is mandatory if Google is offered (App Store rule). | **H** | Phase 1 Authentication; menu data model; Feature 5 Modifier Modal |
| 4 | **Group/party model with shareable join link and per-guest sub-carts** — booking confirmation creates a Party object with invite code; guests join via deep link (works in Scenario B but lifts the live-order block for confirmed party members); each guest gets their own cart that merges at the Phase 4 Checkout screen; "Guest Slots" become real client-side entities, not just waiter-side. | **H** | Phase 2 Booking; Phase 4 Checkout; new "My Party" tab in Phase 3 |
| 5 | **Cancellation, refund, and no-show policy engine** — Phase 2 modify/cancel surfaces an explicit policy ("Cancel free until 18:00, then 50% fee"); cancellation fires a Void event to KDS reusing Feature 7's atomic transaction; refund state added to Order; reservations require card-hold for prime slots; auto-release after grace period; no-show fee charged. Receipts and refund receipts both go to email + in-app history. | **H** | Phase 2 Booking lifecycle; Feature 4 Webhook pipeline; new RefundState on Order |
| 6 | **Modify-after-fire flow ("Add to order")** — Phase 4-style mini-checkout reachable from the active session screen; new items become a child ticket injected at current timestamp into Kitchen Incoming. Items currently in Yellow/InProgress cannot be removed without admin Void; items in Gray/Pending can be canceled client-side. Replaces the deleted "Call Waiter to Order" fallback with a sanctioned digital path. | **H** | Phase 4 Checkout (reused); Kitchen Phase 1 Injection |
| 7 | **Accessibility & WCAG 2.2 AA pass** — non-color status redundancy (icon + label on every Free/Occupied/Reserved tile), accessibility tags on tables (wheelchair, step-free, low-noise, near-restroom) filterable in Phase 2; alternate "list view" for the floor plan; captions/haptics for every audio chime; high-contrast and large-text settings in Phase 3 Profile. | **H** | Phase 2 Floor Plan; Feature 9 Live Floor Plan Engine; Feature 7 Void chime |
| 8 | **Receipt, tipping, GDPR & expense integrations on Phase 3 History** — each history row exposes: VAT-compliant PDF receipt, email/SMS forward, one-tap forward to Expensify/Concur/Pleo, in-app tip-after-meal (with split honored), and a Privacy panel with data export (JSON), delete-account, and marketing-consent toggle. | **M** | Phase 3 History; new "Privacy & Data" section in Profile |

### Honorable mentions (Medium / Low)

- **M — Walk-in waitlist & virtual queue** with SMS/push "your table is ready"; pre-seat menu staging that fires on QR scan at the table.
- **M — Favorites, "My Usual," and loyalty tier** on Phase 3 Profile, with one-tap reorder from History.
- **M — Dietary filters & rich menu UX**: vegan/GF/halal/kosher toggles, allergen icons (EU-14), calorie/macro display, spice level, photo-required, search.
- **M — Push/SMS comms to the diner**: order-fired confirmation, order-ready notification (currently only the waiter is notified), reservation reminders.
- **M — Table-share between guests on one device**: host's phone hands off to each guest's phone via QR, so each guest browses their own menu and adds to the shared cart.
- **L — Pre-order ahead with fire-on-arrival** for Scenario B, gated by deposit.
- **L — Reviews v2**: per-dish rating, waiter rating, anti-abuse rate-limit, public response from restaurant.
- **L — Offline-tolerant client cart with retry queue** so a diner mid-checkout in a basement venue doesn't lose their order.
- **L — Guest-checkout lifecycle**: receipt by email/SMS, post-visit "claim this order" link to upgrade to an account without losing history.
