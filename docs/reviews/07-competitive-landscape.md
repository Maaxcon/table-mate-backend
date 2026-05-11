# TableMate Competitive Landscape Review

> Benchmarks current TableMate spec (docs/architecture-and-workflows.md) against 30+ comparable products across QR-order, POS, reservations, KDS, and pay-at-table categories.
> TableMate's spec headlines: 4 roles (Client/Waiter/Cook/Admin), QR-driven in-venue ordering, Kanban KDS with atomic + batch readiness, live floor plan with WebSocket repaints, strict prepay-only client orders, atomic voids, immutable layout versioning.

---

## H2: QR-Order / Self-Order at Table

### Sunday
- **Better than TM:** AI-optimized tip suggestions (15-20% tip lift); auto-AI Google review responses; bill-split by item/seat/people/custom; "10 seconds to pay" experience; integrates with Lightspeed, Tevalis, Aloha, RES3700, Ikentoo.
- **TM differentiator:** Sunday is bill-pay only on top of existing POS; TM is end-to-end (order + kitchen + floor plan + admin) in one stack. TM's WS-driven dish lifecycle (Gray/Yellow/Green) is finer-grained than Sunday's payment-centric flow.
- **Steal:** (1) Per-item / per-seat bill split UX, (2) AI-suggested tip tiers, (3) Auto-routed Google review prompt post-checkout.

### Mr Yum (now me&u)
- **Better than TM:** Photo-rich visual menus (every dish), "Group Tabs" so multiple guests at one table order independently into a shared tab, "Advanced Batching" which collates separate orders to one kitchen print; 75+ POS/marketing/payment integrations; Afterpay BNPL.
- **TM differentiator:** TM bakes guest-seat assignment directly into the Waiter-led flow with a Modifier Modal (modifier-first ergonomics). Mr Yum is more menu/marketing focused.
- **Steal:** (1) Group Tab — multiple phones one table one open tab, (2) Per-dish photo-first menu cards, (3) Batching logic that groups simultaneously placed orders into a single kitchen ticket.

### GloriaFood (sunsetting, but worth analysing)
- **Better than TM:** Free tier model with pre-ordering, takeaway/delivery, marketing automation, allergen icons, public menu API. Promo-logic builder.
- **TM differentiator:** TM is real-time and operations-first; GloriaFood is ordering-only and lacks a KDS/floor-plan.
- **Steal:** (1) Allergen-free icon system on menu items, (2) Pre-order for future arrival time, (3) Promo/coupon rule engine.

### Bbot (DoorDash Storefront)
- **Better than TM:** "Order alongside servers on a single open tab" — server and customer co-author the same order; tight POS/loyalty/reservation passthrough; works on handhelds & tablets; commission-free white-label.
- **TM differentiator:** TM mandates prepay-only and bans the "call waiter to order" fallback explicitly — operationally cleaner. Bbot is more permissive.
- **Steal:** (1) Shared open tab where waiter and guests both append items, (2) White-label theming per venue, (3) Loyalty passthrough hooks.

### Flipdish
- **Better than TM:** Self-service countertop **kiosk** hardware (K2 Mini); QR + kiosk + delivery from one menu; portal-driven menu/order/payment console; reports 20-30% AOV uplift on kiosks.
- **TM differentiator:** TM's role-isolated UI per-device (Cook/Waiter/Admin) is more rigorous than Flipdish's single console.
- **Steal:** (1) Kiosk mode (read-only big-touch UI on iPad at entry), (2) Upsell/cross-sell suggestions at cart, (3) Single menu source for QR + kiosk + delivery channels.

### BentoBox
- **Better than TM:** Restaurant website builder, gift cards (physical+digital), catering pre-orders up to 1 year out, automated SMS post-order, loyalty rewards engine, events/private dining module, email + SEO marketing.
- **TM differentiator:** TM doesn't try to be marketing/CMS. Operationally cleaner.
- **Steal:** (1) Gift cards (digital), (2) Post-visit automated SMS for review/return, (3) Loyalty point accrual tied to Session totals (TM already logs immutable Session snapshots — perfect substrate).

### SoluM
- **Better than TM:** Hardware-first — ESL digital shelf labels and Newton TOUCH on-table digital signage with allergens, recipes, video; instant pricing updates via wireless tag.
- **TM differentiator:** TM is pure software; doesn't need hardware. SoluM lacks the order/KDS/floor-plan layer entirely.
- **Steal:** (1) Allergen + ingredient drill-down per dish, (2) Multi-language menu auto-translate, (3) Video/cooking-demo slot on menu cards.

### Tabesto (by Deliverect)
- **Better than TM:** Cross-sell/upsell engine on kiosk + QR ("frequently together", combos); meal-ticket and cash payments alongside cards; Apple/Google Pay; integrated with Uber Eats / Deliveroo; 15-30% basket-size uplift claimed.
- **TM differentiator:** TM enforces prepay only on client side — no cash. That's cleaner ops but loses some guests.
- **Steal:** (1) Combo/upsell suggestions inside the Modifier Modal, (2) Discount/promo codes at checkout, (3) Uber Eats / Deliveroo aggregator-channel injection into the same Incoming column.

### Yoello
- **Better than TM:** FCA-authorised payment institution itself (multi-vendor single-QR for food halls/markets); evenly-split bill or custom-amount split; NFC tap-to-order at table; web-only (zero app).
- **TM differentiator:** TM's Kanban + Batch View KDS is more elaborate than Yoello's order-pipe.
- **Steal:** (1) NFC table sticker as alternative to QR, (2) Multi-vendor single-table model (e.g. food court), (3) Guest checkout with zero registration.

---

## H2: Full Restaurant POS

### Toast
- **Better than TM:** KDS with "all-day" production count view ("how many burgers in the oven right now"); ticket-time alerts; multi-channel ingest (dine-in + takeout + delivery + curbside) into one KDS; drive-thru module; payroll, inventory, banking, capital.
- **TM differentiator:** TM's atomic-tap per-item readiness with WS pulse-back to floor plan is more granular than Toast's ticket-level KDS. TM's prepay rule eliminates a class of mis-fires.
- **Steal:** (1) All-day item count panel on KDS, (2) Ticket-time SLA color alarms (red after X minutes), (3) Multi-channel single-queue ingest.

### Square for Restaurants
- **Better than TM:** Multiple named floor plans per venue (lunch vs dinner layout); KDS routing by station with custom ticket timers; color-coded long-wait labels; included free with Plus plan.
- **TM differentiator:** TM has immutable JSON-versioned floor-plan history with WS hot-publish; Square is simpler. TM enforces zero local-state inference on the floor plan (server is source of truth) — Square is looser.
- **Steal:** (1) Multiple named layouts (lunch/dinner/private event), (2) Per-station KDS routing rules, (3) Auto color-flip when table sits too long without order.

### TouchBistro
- **Better than TM:** True tableside server flow, time-seated and spend-per-table monitoring, fine-dining table-management heritage.
- **TM differentiator:** TM has explicit Cook/Waiter/Admin role separation; TouchBistro is generalist.
- **Steal:** (1) Spend-per-table widget on the floor-plan tile, (2) Time-since-last-course warning, (3) Server-section assignment per shift.

### Lightspeed Restaurant (K-Series)
- **Better than TM:** Per-station KDS routing ("Grill", "Bar", "Cold"); items routed automatically by category; **explicit Course management (course-by-course firing or seat-by-seat)**; multiple adjustable floor plans; KDS 2.0 with bump-bar.
- **TM differentiator:** TM Batch View is unusual for cross-ticket aggregation; Lightspeed routes per-station but doesn't aggregate across tickets the same way.
- **Steal:** (1) Course fire (appetiser/main/dessert sequencing), (2) Per-station KDS routing by item category, (3) Order-by-seat vs order-by-course toggle.

### Clover
- **Better than TM:** Modular hardware ecosystem (Flex Pocket handheld $699 / $35-mo), tap/dip/swipe at table; KDS color-coded prioritisation; consolidates online + in-house orders; large app marketplace.
- **TM differentiator:** TM doesn't lock to hardware; Clover is hardware-led.
- **Steal:** (1) Handheld payment terminal handoff to waiter, (2) App-marketplace plugin architecture, (3) Online-order consolidation into in-house KDS.

### Revel
- **Better than TM:** Distinct Cook View vs Expedite View; staff names attached to tickets; modifier passthrough; customer name on ticket; loyalty + gift cards + CRM stitched into POS.
- **TM differentiator:** TM has BUMP semantics tied to all-items-ready; Revel is more traditional.
- **Steal:** (1) Expo display variant (read-only ticket overview for an expediter), (2) Waiter name + guest name on every kitchen ticket, (3) Bump-bar hardware support.

---

## H2: Reservations + Floor Plan

### OpenTable
- **Better than TM:** Electronic Reservation Book + waitlist with SMS-when-ready; POS-driven auto-statusing; **server-section assignment** with running cover counts; reservation distribution via OpenTable's diner network.
- **TM differentiator:** TM has an interactive spatial floor plan that's the same canvas for booking AND service — OpenTable separates them more.
- **Steal:** (1) Waitlist with SMS-when-ready (huge: TM has zero walk-in queue), (2) Server-section assignment + cover counts, (3) Public diner-facing booking network.

### Resy
- **Better than TM:** Customer recommendations engine, exclusive events/promotions, polished consumer brand.
- **TM differentiator:** TM owns the in-venue full session, not just the booking moment.
- **Steal:** (1) "Notify me" waitlist for fully-booked nights, (2) Pre-paid event/tasting-menu tickets, (3) Diner profile with prior visit history surfaced to the host on arrival.

### SevenRooms
- **Better than TM:** CRM with birthdays/dietary restrictions/VIP flags; loyalty program; QR-shareable waitlist; "prioritise high-value guests" on waitlist; deep marketing automation.
- **TM differentiator:** TM has live operational state (kitchen + floor + voids) that SevenRooms doesn't try to do.
- **Steal:** (1) Guest profile with allergies/dietary/birthday auto-surfaced when a booked guest arrives, (2) VIP tag with priority routing in the kitchen, (3) Birthday SMS marketing trigger.

### Yelp Guest Manager
- **Better than TM:** Public discovery via Yelp; review aggregation; waitlist + reservations + table management in one; SMS notifications.
- **TM differentiator:** TM is white-label; Yelp brands the platform.
- **Steal:** (1) Public review aggregation widget, (2) Two-way SMS waitlist communication, (3) No-show tracker per guest.

### Tock
- **Better than TM:** **Prepaid reservation / deposits** — exactly TM's philosophy applied to bookings ($5 deposits cut no-shows to 1.7%); credit-card holds; charge-on-no-show; multi-policy (deposit vs full prepay vs hold) per shift; tasting-menu ticket sales.
- **TM differentiator:** Tock doesn't run the in-venue session.
- **Steal:** (1) **Booking deposit / no-show charge** — perfectly aligned with TM's prepay culture, (2) Credit-card hold for high-value bookings, (3) Sell tasting-menu seats like event tickets.

### Eat App
- **Better than TM:** Server section management, shift-level reservation rules, sustainability/recurring-guest analytics.
- **Steal:** (1) Shift-based reservation rules (no 6-tops after 9pm), (2) Recurring-guest analytics, (3) Reservation source attribution (Google, Instagram, walk-in).

---

## H2: Kitchen Display Systems

### Toast KDS
- **Better than TM:** All-day production count, multi-channel ingest into a single board, ticket-time aging alarms, durable kitchen-grade hardware.
- **Steal:** (1) All-day prep aggregate panel, (2) Aging-ticket color-alarm escalation, (3) Stuck-ticket / overdue audio escalation.

### Square KDS
- **Better than TM:** Custom ticket timers, multi-device sync, per-station performance reports.
- **Steal:** (1) Per-station prep-time KPI breakdown (TM only tracks total cycle time), (2) Custom timer thresholds per item, (3) Multi-device sync with role per device.

### Fresh KDS
- **Better than TM:** **Coursing** (course labels group items, headers above sections); **guest seat numbers** on every item; **86-ing from KDS** (cook flips a sold-out item, instantly grays POS & online); recall-from-completed.
- **TM differentiator:** TM's Batch View is unusual; Fresh focuses more on coursing.
- **Steal:** (1) **86-list from the KDS itself** (TM only has Admin Emergency Stock Toggle — too slow), (2) Coursing headers (Apps / Mains / Desserts), (3) Recall-from-COMPLETED for missed items.

### Squadle
- **Better than TM:** Food-safety + temperature monitoring tied to KDS; HACCP digital logging; allergen routing.
- **Steal:** (1) Allergen-flag on tickets that auto-routes to a separate "Allergen" prep station, (2) HACCP/temperature log per station, (3) Refrigeration/equipment monitoring tied to the dashboard.

### Oracle Simphony KDS
- **Better than TM:** **Prep vs Expo display types** (prep stations vs expediter overview); **priority levels 1-8** on tickets via Expo; IP-54 rated kitchen hardware; multi-property roll-up.
- **Steal:** (1) Separate Expo screen view (read-only summary across stations), (2) Manual priority bump 1-8 (VIPs, allergens, retries), (3) Prep-station-vs-expo separation in TM's KDS UI.

---

## H2: Pay-at-Table / Split Bill / Tipping

### Sunday (covered above)
- Plus: tip-jar feature that splits tips across staff; review-deflection (5-star to Google, <5-star private email to manager).

### MyCheck
- **Better than TM:** 4-digit table-code pairing (no QR needed), split bill across multiple phones using same code, slide-to-tip UX, loyalty card stamps, email receipt.
- **Steal:** (1) **Multi-phone bill-share via short code** — guests join the same bill from their own devices, (2) Slider-tip UX (vs fixed buttons), (3) Auto-loyalty stamp on every paid session.

### Sezzle (BNPL relevant)
- **Better than TM:** Buy-now-pay-later for higher-ticket dining.
- **Steal:** (1) BNPL option for >$X tickets, (2) Group split where each diner picks their own payment method including BNPL.

### Adyen Tap to Pay
- **Better than TM:** **Tap-to-Pay on Android phone — no terminal hardware required**; tip amount per split; tip attributed to authenticated server (no later adjustment); auto-fallback Wi-Fi-to-cellular on terminals.
- **TM differentiator:** TM is prepay-only on client — but waiter-led flow has no payment yet.
- **Steal:** (1) **Waiter phone as a tap-to-pay terminal** for waiter-led table close, (2) Tip attributed to logged-in staff member, (3) Per-staff tip ledger feeds tip-pool reporting.

---

## H2: Gaps That No Role-Review Will Catch

These are operational realities TableMate's role-walk doesn't expose. Each is a feature decision, not just polish.

1. **86 / Sold-Out list from KDS, not Admin only.** TM puts stock toggle in Admin only; cooks know first. Fresh KDS lets cooks flip an item sold-out and it cascades to POS + online instantly. Without this, prepay clients will order items that are already out.
2. **Course pacing & coursing labels.** TM tickets fire as one block. Real fine dining needs Appetiser → Main → Dessert firing in stages, with the kitchen marking a course "complete" before the next fires. Lightspeed, Fresh, Toast all support it.
3. **Tip pool / per-staff tip attribution.** TM has no tip model at all. Adyen + Toast attribute tip to the authenticated server; many jurisdictions require this for tax. TM's prepay flow needs a tip step (Apple Pay tip prompt at minimum).
4. **Accessibility — A11y / large-text / screen-reader / color-blind palette.** TM uses Gray/Yellow/Green as the lifecycle. ~8% of male guests are red-green deficient, so Yellow vs Green can fail. Add patterns/icons, not just color. Also Waiter UI must support iOS VoiceOver for accessible-hire compliance in EU.
5. **Loyalty + SMS / email marketing.** TM has zero CRM/marketing. BentoBox, SevenRooms, Sunday all turn one visit into return visits. Session snapshots are the perfect substrate — wire a Loyalty service that listens to "session_closed" events.
6. **Table merge / split / transfer.** TM has Open → Close on a table. Real ops: 4-top arrives expecting a booked 6-top, you merge two 4-tops; a couple decides to move tables mid-meal, you transfer the open Session. Every POS supports this; TM doesn't model it.
7. **Host stand vs server roles.** TM has Waiter as a single role. OpenTable, SevenRooms, Eat App differentiate Host (seats guests, manages waitlist, assigns sections) from Server (works specific section). At scale these are different humans with different permissions.
8. **Walk-in waitlist with SMS-when-ready.** TM only supports pre-booked Reservations and walk-in seating into a Free table. No queue when fully booked. OpenTable/Yelp/SevenRooms all have this and it's a major top-of-funnel feature.
9. **Deliveroo / Uber Eats / DoorDash channel injection.** TM's Incoming column only ingests in-venue orders. Real restaurants split 30-50% of revenue across delivery aggregators. Need a Deliverect/Otter-style channel adapter so 3rd-party tickets land in the same Kanban with a channel badge.
10. **Kiosk mode.** TM has Client (phone), Waiter (tablet), Cook (tablet), Admin. No Kiosk. Flipdish/Tabesto report 20-30% AOV uplift on a kiosk. Add a locked-down full-screen variant of the Client UI on an entry-stand iPad.
11. **Offline-first KDS.** TM AC 12.2 hard-disables writes when WS drops. In a kitchen, that's a service-stopper — Wi-Fi dies and the line freezes. Production-grade KDS (Toast, Oracle) keep a local cache and reconcile on reconnect; cooks keep bumping tickets even offline.
12. **Per-station KDS routing.** TM has one Kanban for all cooks. Real kitchens have Grill / Sauté / Cold / Pizza / Bar — each a different screen with only their items. Lightspeed, Toast, Oracle all do this; without it, a 12-station kitchen sees 12x the noise.
13. **Allergen / dietary metadata + allergen-routing.** TM menu items are price + name + modifier. No allergen tags. SoluM, GloriaFood, SevenRooms surface this; some KDS auto-route allergen items to a separate prep area.
14. **Gift cards & vouchers.** Revenue feature, not operational. BentoBox, Toast, Square all sell them.
15. **Reservation deposits / no-show charges.** TM allows free cancel from Active Bookings — perfect no-show vector. Tock built a business on the opposite. Even a $5 hold drops no-shows to 1.7%.
16. **Cover counts & pacing metrics on the floor plan.** OpenTable shows per-server live cover count. TM shows time-at-table ring + running bill, but not how many covers a server is currently carrying.
17. **Multi-floor / multi-room / multi-location.** TM has one floor plan per restaurant. Real chains need outlets/multi-property; even single restaurants have patio vs main vs bar. Square supports multiple layouts; TM should too.
18. **Group Tab / shared cart on one table.** TM treats each guest seat as a slot one client owns. Mr Yum's Group Tab lets 6 phones order onto one open tab. Without it, group prepay UX is awkward (one person pays, everyone owes them).
19. **Cancel / refund / chargeback flow.** TM has Void mid-service. No refund-after-checkout flow if a client disputes. Stripe/Adyen require a handler.
20. **Recall-from-Completed.** TM moves tickets to COMPLETED via BUMP. If a server realises a dish was forgotten, there's no recall. Fresh KDS, Oracle Simphony both allow recall.
21. **Receipt & VAT/tax compliance.** EU requires fiscalisation in many countries (Italy, Greece, Germany TSE, France NF525). TM's "saves immutable Session snapshot" is a start; needs proper fiscal receipt signing and chained hashes.
22. **Multi-language.** TM has language setting in profile — no detail on menu i18n. Mr Yum / SoluM auto-translate; critical for tourist-heavy venues.
23. **Voice / printer fallback for KDS.** Power cut to the screens? Most kitchens still have a thermal printer fallback. TM is digital-only.

---

## Cross-Cutting Verdict

- **Where TM is genuinely competitive:** prepay-only enforcement (Tock-grade no-show prevention applied to ordering), atomic-tap dish lifecycle with cross-system WS pulse, Batch View aggregating identical items across tickets (rare), immutable versioned floor-plan publish, role-scoped WS event broadcasting with replay-on-reconnect.
- **Where TM is borrowed/standard:** Kanban KDS, drag-drop floor plan editor, role-based JWT, Apple/Google Pay checkout, real-time dish status colors.
- **Top 5 highest-ROI features to steal first:** (1) 86-from-KDS, (2) Course firing & coursing labels, (3) Per-station KDS routing, (4) Reservation deposit / no-show hold (Tock model), (5) Waitlist with SMS-when-ready.
