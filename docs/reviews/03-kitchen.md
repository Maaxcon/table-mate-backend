# TableMate Kitchen Spec Review — Line Cook / Expediter POV

Reviewed: `/Users/oleksandrstepanenko/unibrix/ table-mate/table-mate-backend/docs/architecture-and-workflows.md`
Focus: PART 3 (Kitchen), with checks on Waiter Phase 3/4 handoff and Admin Void / 86 flows.

I'm wearing whites. It's a Saturday, 47 covers on the board, two deuces just walked in. Here's what the spec gets wrong from where I'm standing at the pass.

---

## 1. Station Routing — No per-station view

**Spec gap.** Phase 1 says all tickets land in a single `INCOMING` column "strictly ordered by injection timestamp" (also reinforced by Feature 6 AC 1). In a real kitchen, a ticket for Table 12 with a Caesar (cold/garde manger), a 25-min duck (sauté/grill), and a creme brulee (pastry) needs three different cooks to see only their relevant lines, not the whole ticket. The doc never models stations.

**Concrete fix.**
- Add a `Station` entity per restaurant (Grill, Sauté, Cold, Pastry, Fry, Pass) configurable in Admin Phase 4.
- Add a `MenuItem.station_id` (or `prep_routes[]` for multi-station items, e.g. burger = grill + fry).
- KDS layout: each station screen filters Active/Incoming items where `item.station_id == screen.station_id`. Expo screen sees the whole ticket. Cooks bump items, not tickets; expo bumps tickets.
- Backend event: `ItemRouted{ticket_id, item_id, station_id}` fires on injection.

---

## 2. Course Firing — Phase 1 mentions only injection, never courses

**Spec gap.** Real service: apps fire on seat, mains hold until expo calls "fire mains" (usually 2-3 min after apps cleared). Spec has one shot: ticket lands, everyone cooks. A grill cook seeing the whole ticket will start the duck at injection and it'll die under the heat lamp while guests are still on the Caesar.

**Concrete fix.**
- Add `OrderItem.course` (App, Main, Dessert, Side) at menu config; default per item, editable per order.
- Lifecycle additions: `Hold` state between `Pending` and `In Progress`. New ticket-level action `FireCourse(course)` (waiter or expo triggered).
- Add `auto_fire_after_seconds` per course (configurable; many places fire mains 8 min after apps fire). Manual override always available.
- WS event `CourseFired{ticket_id, course}` un-greys items at relevant stations.

---

## 3. Cook Time / Backwards Timing — No prep-duration model

**Spec gap.** Doc lists statuses Gray/Yellow/Green but no `MenuItem.prep_minutes`. A 25-min duck and 4-min salad fired together = salad wilts or duck is late. Real KDS (Toast, Square KDS, Aloha) show a "start by" countdown derived from `target_pickup_time − prep_minutes`.

**Concrete fix.**
- Add `MenuItem.prep_minutes` (and optional `MenuItem.rest_minutes` for proteins).
- Compute `target_pickup_at = max(item.prep_minutes for items in same course on ticket)` at fire-time.
- Per item show `start_by = target_pickup_at − item.prep_minutes`.
- Station screen sorts by `start_by` ascending, not by injection timestamp. Items past `start_by` flash amber.

---

## 4. Expediter / The Pass — Role doesn't exist

**Spec gap.** Roles in Feature 1 AC 1 are Cook, Waiter, Manager, Owner. No Expo. Phase 4 says "the cook taps the last item, the BUMP button activates." In any kitchen above bistro-level, the cook does not own the pass — expo wipes plates, marshals the ticket, and bumps. Without expo, the runner pulls food piecemeal, or worse, eight cooks all think someone else is calling pickups.

**Concrete fix.**
- Add `Role.Expediter` to RBAC ENUM (Feature 1).
- Expo screen view: full ticket with cross-station status, garnish/plating checklist, and exclusive `BUMP` authority (cook-only bump is a Restaurant Setting toggle for small kitchens).
- New status `Plated` (between item-Green and ticket-Bumped) — cook marks plated when it hits the pass, expo bumps when complete tray leaves.

---

## 5. Recall / Refire — Not modeled

**Spec gap.** Void (Admin Phase 2) marks an item red with "VOID" stamp and a chime. That's a cancellation, not a refire. If guest sends steak back ("too rare"), we need to remake just that item, keep the rest of the ticket history, and tag the refire as no-charge with a reason. Spec has no concept.

**Concrete fix.**
- New action `Refire(item_id, reason_code, no_charge: bool)`. Reason codes: GuestReturn, DroppedInKitchen, WrongDoneness, Allergen, Mispick, RushReplace.
- Creates a new `OrderItem` linked via `refire_of` FK with `is_refire=true`, fresh lifecycle, badge on KDS "REFIRE — DO NOT REBILL".
- Refires jump to the top of the station queue (configurable priority) with a distinct red border.
- Audit trail in Admin Phase 5 next to Void Ledger.

---

## 6. Cook-Initiated 86 — Wrong actor

**Spec gap.** Admin Phase 4 has "Emergency Stock Toggles." But the person who knows we're down to two salmon is the sauté cook counting portions in the lowboy. Forcing them to call the manager (who's at table 7 selling wine) loses 5 minutes. Spec has no cook permission to 86.

**Concrete fix.**
- Add cook-facing `86 / Low Count` action on each menu item from KDS (long-press item card).
- Two modes: `Set Count Remaining: N` (auto-86 when waiter orders the Nth) and `86 Now` (instant block).
- Manager gets a notification, can override. Items in already-fired tickets are unaffected; only new injections blocked.
- RBAC: grant Cook permission `menu.set_stock_count` (toggleable per restaurant).

---

## 7. Allergy & Dietary Visibility — Hidden in comment field

**Spec gap.** Waiter Phase 4 step 2: "Modifier Modal immediately appears for comments (e.g., 'No onions')." Feature 5 AC 2 focuses input on a Comment field. "NUT ALLERGY" typed in free text could be in 8pt grey, missed, kill someone. Modifier modal has no structured allergen field.

**Concrete fix.**
- Structured `dietary_flags[]` on OrderItem: `NUT_ALLERGY`, `GLUTEN_FREE`, `DAIRY_FREE`, `SHELLFISH`, `VEGAN`, `VEGETARIAN`, `HALAL`, `KOSHER`, custom.
- KDS rendering: any allergy flag → full red border, white-on-red banner across top of card "ALLERGY: NUTS", plus distinct audio cue ("allergy ticket" — different from new-order chime).
- Allergy items require explicit `Acknowledge Allergy` tap before `Start Item` enables (slows it down on purpose).
- Expo must re-confirm at pass — second-check pattern, like marine bridge calls.

---

## 8. Partial Bump — Locked out by spec

**Spec gap.** Feature 6 AC 3 + Phase 4 step 1: BUMP "strictly disabled until every single item within that ticket has been tapped and moved to Completed." Cook can't tell the runner "the wings are up, take them now." This forces apps and mains to bump together, which destroys course service.

**Concrete fix.**
- Item-level bump already exists (atomic tap). Re-conceptualize: atomic tap = "ready at pass / runner can pick up this dish now." Ticket-level BUMP = "everything off our board, close the ticket."
- Send runner notification per `ItemReady` event, not per ticket bump.
- Show `Partial Bump` button per course: lets the cook signal "this course is complete, runner go now" without waiting for the entire ticket.
- Keep all-green requirement only for the final ticket close.

---

## 9. Batch View Mass Notification — Floor confusion

**Spec gap.** Phase 3: batch-bumping "8x Burgers" simultaneously alerts 8 different waiters at the same instant for 8 different tables on different fire timings. Tables 4, 7, 12 may all be mid-app — their burgers shouldn't be claimed yet. Also: who actually plates 8 burgers in the same 5 seconds? They won't all be ready together — buns toast at different times, garnishes added per-order.

**Concrete fix.**
- Batch view shows a list of `pending burger` items grouped, but each item is bumped individually as it's actually plated. Drop the "mark all 8 ready at once" pattern — it's wishful thinking.
- If keeping batch-bump, require it to respect each item's `fired_at` timestamp + per-ticket course-fire state — only items whose course has been fired and whose ticket isn't holding are eligible.
- Runner-side: surface a "runner queue" view that groups ready items by table, so a runner walks one tray of three tickets' worth of burgers rather than three trips.

---

## 10. Active Claim Contention — No locking model

**Spec gap.** Phase 1 step 2: "A cook taps the ticket header, moving it to ACTIVE." Two cooks tap simultaneously on two tablets. Race condition undefined. Also: in a station model, a ticket isn't owned by one cook — grill owns the steak, sauté owns the risotto. "Single claim" assumption is wrong.

**Concrete fix.**
- Drop ticket-level claim. Replace with item-level claim: each `OrderItem` has `claimed_by_user_id` and `claimed_at`. Optimistic-lock with `ETag` / version number on item.
- If two cooks tap, server returns 409 to the second; UI shows "Claimed by Marco — release?" with manager override.
- Station-bound ownership: a Grill-station-token cook can only claim grill items. Reduces collisions.
- Auto-release if no progress after N minutes (cook walked off / tablet froze).

---

## 11. Audio / KDS Hardware — Only one chime mentioned

**Spec gap.** Feature 7 AC 3 mentions a "KDS audio chime" on void. No cues defined for: new order, new fire (course fired), allergy ticket, late ticket, refire, 86 confirmation, station handoff. A kitchen runs on sound — cooks aren't staring at the screen, they're flipping. Also: no spec for screen brightness, anti-grease bezel, kitchen-display hardware requirements (touch with greasy gloves, no keyboard).

**Concrete fix.**
- Define audio token set: `new_order.wav`, `course_fired.wav`, `allergy.wav` (loud, distinct), `refire.wav`, `late_ticket.wav` (escalating), `void.wav`, `bump_confirmed.wav`. Volume per station, configurable in Admin.
- Visual reinforcement: header bar pulses color matching cue.
- Hardware requirements doc: bump-bar support (USB HID for physical bump buttons), wipeable touch screens, sticky-touch tolerance (require ≥250ms hold for destructive actions, not 100ms tap), no swipe-to-delete (greasy fingers misfire).

---

## 12. Dwell / Late Ticket Escalation — Unspecified

**Spec gap.** Backend logs Total Cycle Time (Phase 4 step 3) and Admin sees Average Prep Time (Feature 11 AC 1), but the KDS itself has no real-time dwell display. A ticket 18 min old when average is 9 min should be visually screaming. Cycle-time logging is for analytics, not for the cook on the line.

**Concrete fix.**
- Each KDS card shows `elapsed_since_fired` (mm:ss) always visible, top-right.
- Visual escalation tiers (configurable per restaurant): green 0-target, amber target → target×1.25, red target×1.25+. Flash at target×1.5.
- Late tickets bubble to the top of the column with a red ring.
- WS event `TicketLate` notifies expo + manager when crossing red threshold.

---

## 13. Conflicting Modifiers — Spec ignores

**Spec gap.** Waiter Phase 3 step 3 mentions "final check for conflicting modifiers" — implies humans catch it. Modifier modal (Feature 5) is free-text comment. "No onions" + "extra onions" on the same dish will print both and the cook has to guess.

**Concrete fix.**
- Replace free-text-only with a structured modifier system: each menu item has a `modifiers_schema` (e.g., onion: none/normal/extra; doneness: rare/mr/m/mw/well). Free-text comment field is supplementary, not primary.
- Server-side validation: mutually exclusive modifier values rejected at order-submit with `409 ModifierConflict`.
- KDS card renders modifiers as colored chips, not buried prose. Negatives in red ("NO onion"), additions in green ("+bacon").

---

## 14. Recipe Reference for New Cook — Not in spec

**Spec gap.** Spec assumes the cook knows the dish. New hire on Saturday night? Plating reference, ingredient list, allergens for the dish itself? Nothing in the doc links menu items to a recipe / plating view from KDS.

**Concrete fix.**
- Add `MenuItem.recipe_id` → recipe entity with: ingredient list (links to inventory for auto-86), method steps, plating photo, allergen content, default modifiers.
- Long-press item card on KDS opens recipe overlay (non-destructive, doesn't claim the ticket).
- Admin Phase 4 menu management gets a Recipe editor tab.
- Bonus: allergen content auto-cross-references guest dietary flags and warns at order-entry time, not just at the pass.

---

## Other things I'd flag while I'm here

- **No "all day" totals** ("all day, 14 ribeyes, 6 medium, 4 mr, 4 well") — essential for grill cook batching protein.
- **No printer fallback.** When the network dies mid-rush, the spec disables all writes (Feature 12 AC 2) — but a real kitchen needs a paper-ticket fallback printer or it stops dead.
- **No fire-time-from-seat tracking.** Waiter Phase 3 fires when waiter taps; no concept of "seated 10 min ago, fire apps now."
- **No comm channel cook → waiter.** Cook can only mark dishes Green. Can't say "this duck will be 5 more, comp the table a starter?"
- **Reservation prep:** kitchen has zero visibility on the booking floor — a 12-top arriving in 30 min should pre-warn the line for mise. Phase 1-3 admin/booking flow does not push anything kitchen-ward.
- **Shift handover.** Mid-shift cook swap — no concept of in-progress item reassignment.
- **Item-level photos for runners.** Runner sees a name "Salmon"; with 4 salmon dishes on the menu, photo would help routing.

---

## Top 10 Kitchen-Facing Improvements (priority)

| # | Improvement | Priority | Why |
|---|---|---|---|
| 1 | Station routing + per-station KDS view | **H** | Single Incoming column is unusable in any kitchen with >1 station. Foundational. |
| 2 | Course states + Fire Mains action | **H** | Without this, every ticket cooks at once; food dies under heat lamps. Core service model. |
| 3 | Structured allergen flags + visual/audio escalation | **H** | Safety. Free-text comments will kill someone eventually. |
| 4 | Expediter role + Plated/Bumped distinction | **H** | No one marshals the pass; runners pull food piecemeal. |
| 5 | Per-item prep_minutes + backwards timing | **H** | 25-min duck and 4-min salad can't both land hot together without it. |
| 6 | Refire workflow with no-charge audit | **H** | Voids ≠ refires. Today no way to remake a returned dish without rebill chaos. |
| 7 | Cook-initiated 86 / count-remaining | **M** | Faster sold-out propagation; cook is closest to ground truth. |
| 8 | Partial / per-course bump + runner notifications | **M** | Course service breaks under "all-green ticket BUMP" rule. |
| 9 | Late-ticket dwell display + audio escalation tiers | **M** | Cooks can't read analytics dashboards mid-rush; needs in-screen escalation. |
| 10 | Structured modifier schema + conflict rejection | **M** | Stops the no-onion/extra-onion class of bugs at source. |

Honorable mentions (L): recipe reference overlay, all-day totals, item-level claim locking, network-down printer fallback, runner queue grouping.

---

End of review. Now I have to go plate four ducks. Service.
