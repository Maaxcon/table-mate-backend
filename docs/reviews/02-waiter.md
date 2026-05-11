# TableMate Waiter Workflow Review — Friday/Saturday Night Reality Check

Reviewer hat: a working waiter with 7 tables, two seatings, a four-top that just got merged with a deuce, and a kitchen that just 86'd the salmon. Spec under review: `docs/architecture-and-workflows.md` PART 2, with handshakes from PART 1 (Client) and PART 3 (Kitchen).

---

## Scenario 1 — Section assignment (my 7 tables vs the whole map)

**Spec says:** "The waiter logs in and lands on the **Live Occupancy** floor plan" with Free / Reserved / Occupied colors. Admin Phase 3 mentions "groups them into Sectors" in the spatial editor. Feature 1 RBAC encodes role into JWT but says nothing about section assignment.

**Gap:** There is no concept of "this waiter is assigned to section B tonight." A waiter on a 60-table floor sees all 60. Notifications in Phase 2 (Sidebar Alerts) say "Table 12 is requesting a waiter" — to whom? Every waiter? On a Friday night with 8 waiters, a single ping going to everyone is noise; a ping going to no one (because we forgot to assign) means a guest waits 15 minutes.

**Concrete fix:**
- Add `ShiftAssignment` model: `waiter_id`, `section_id`, `start_at`, `end_at`. Admin sets it in a "Tonight's floor" screen at pre-shift.
- WebSocket events become section-scoped: a Waiter token receives `OrderUpdated` / `TableRequest` only for tables in its current section (plus a "Backup waiter" overflow rule).
- Floor plan default-filters to the waiter's section with a toggle "Show full floor" for awareness. Out-of-section tables render at 30% opacity, untappable except by a Manager role.

---

## Scenario 2 — Tables joined (two 4-tops pushed together)

**Spec says:** Nothing. Tables are atomic entities with a fixed `capacity` set in the Admin Spatial Editor. Session is `1:1` with Table per Feature 3 AC1.

**Gap:** Big one. Guests join tables constantly — 2 four-tops become an 8-top, a deuce gets added to a six-top to make a seven. The current model has no "merged session." Consequences:
- I can't take one order for 8 people across 2 tables — I'd have to split into two tickets, two bills, two BUMPs.
- The map is wrong: T-04 and T-05 are still drawn as separate occupied rectangles. Admin Mini-Map "Time-at-Table Ring" will diverge between them.
- Closing the table only closes one half; the other shows phantom occupancy.

**Concrete fix:**
- Introduce a `TableGroup` (a.k.a. "merged session") concept. A waiter long-presses two adjacent Free tables on the map and taps "Merge" — a single Session is created with `member_tables: [T-04, T-05]` and `effective_capacity = sum`.
- Floor plan renders a dotted polygon hull around merged tables.
- Closing the merged table un-merges atomically and frees both tables back to white.
- WebSocket: emit `TableMerged` / `TableUnmerged` events; KDS shows ticket header as "T-04+05".

---

## Scenario 3 — Course pacing ("fire mains after apps cleared")

**Spec says:** Send to Kitchen is a single button. Order is one shot. Kitchen `INCOMING` is "strictly ordered by injection timestamp."

**Gap:** No course concept. In real life every entree order has implicit courses (apps, mains, dessert) and the waiter holds the mains until apps are bussed. With the current spec, if I send all items, the kitchen fires everything and the mains land cold next to half-eaten apps. If I hold the order in draft and send mains 20 minutes later, I forget — and the kitchen has no idea apps even went out.

**Concrete fix:**
- Add a `course` field to `OrderItem` (enum: Appetizer / Main / Dessert / Drink, plus a `fire_when` enum: Immediate / Hold / On-Cue).
- The Modifier Modal gets a "Course" picker (defaults from menu item's category).
- New ticket state in Kitchen Kanban: `HELD` column for Hold/On-Cue items; held items don't show in INCOMING until the waiter taps "Fire Course 2" on the table view.
- "Fire Course 2" can also be auto-triggered when Course 1's last item is marked Served by the waiter (configurable per restaurant).

---

## Scenario 4 — 86 in the middle of an order

**Spec says:** Admin Phase 4 has "Emergency Stock Toggles: If an ingredient runs out, a single tap marks it 'Sold Out,' instantly graying it out on Waiter tablets and the Client app."

**Gap:** Two issues.
1. **Latency of awareness.** Spec assumes admin does the toggle. The cook is the one who actually runs out of salmon — by the time they tell the manager, the manager toggles it, the WS fires, and my tablet updates, I've already taken 3 orders for salmon at the table.
2. **No retroactive impact alert.** If I've already added salmon to a draft order (not yet sent) when the 86 fires, the spec doesn't say my draft auto-flags the item. Worse, what about an in-flight `INCOMING` ticket that hasn't been claimed? The Void flow is admin-only (Feature 7), so a sold-out item already in the kitchen needs Admin to void each table.

**Concrete fix:**
- Give Cooks a "Mark 86" button on the Kitchen Kanban item card. One tap fires the same `StockSoldOut` WS event; Admin is just notified, not the bottleneck.
- On the Waiter tablet, fire a *blocking modal*: "SALMON SOLD OUT — affects Tables 4, 9, 12 (draft) and Table 7 (in-flight). Tap each to resolve." Each row offers "Suggest substitute" / "Remove" / "Notify guest at table."
- Draft orders with the now-sold-out item highlight the offending line in red and disable Send until resolved.

---

## Scenario 5 — Shift change at 10pm, table 12 still mid-meal

**Spec says:** Nothing. Waiter logs in (Phase 1), waiter closes table (Phase 5), no mention of handoff.

**Gap:** Every restaurant has shift changes. The outgoing waiter needs to hand T-12 to the incoming waiter with context: "Mains just dropped, they want one more bottle of red, the guy on seat 3 is allergic to shellfish, comp the dessert because their wine was off." None of that is captured. Today they'd Slack each other or shout across the pass.

**Concrete fix:**
- Per-Session "Handover Notes" free-text field on the Table Detail Overlay, plus structured "Open Tasks" checklist (e.g., "Drop second bottle of Malbec", "Comp the tiramisu").
- "Reassign Waiter" action on a table: pick the incoming waiter from the active shift roster, the table flips owner in WebSocket, both waiters see a confirmation toast.
- Pre-shift "Open Tables" dashboard for the incoming waiter showing inherited tables with notes pinned at the top.

---

## Scenario 6 — Voiding / Comping a steak

**Spec says:** "Void Initiation: To correct errors, the Admin swipes an item and taps the Red Trash/Void Icon." Feature 7 AC1 puts the modal strictly in admin land.

**Gap:** On a Friday night the manager is on the phone with a vendor or expediting at the pass. If the only path to void is the admin tablet, the guest waits 6 minutes for a refire. Also, there's no concept of *comp* (zero out the line, keep it on the ticket for inventory & guest satisfaction tracking) vs *void* (item never happened).

**Concrete fix:**
- Add `void_request` flow: waiter taps "Request Void" on an item, picks Reason Code, optionally adds a photo (overcooked steak proof). The request goes to a Manager queue with high-priority WS alert. Approval is one tap.
- Add a separate `Comp` action (manager-approved, distinct reason codes: Service Recovery, VIP, Marketing). Comp keeps the item in inventory and in the Average Prep Time KPI but zeros the financial line and stamps it on Void Audit Trail with `kind=comp`.
- Below a per-restaurant configurable threshold (e.g., $15), waivers can be auto-approved by the waiter with a daily cap.

---

## Scenario 7 — Split bill (3 cards, 1 cash, table of 6)

**Spec says:** "Once all items are served and the bill is paid, the waiter taps Close Table." That's it. The only payment flow described is Phase 4 Client checkout (Apple Pay / Google Pay / Card) for prepaid orders.

**Gap:** No waiter-side payment UI at all. Splitting by item, by share, by seat, mixed tender — the entire end-of-meal reality is missing. Tip handling (next scenario) is also undefined.

**Concrete fix:**
- New Phase 6 in Waiter Workflow: "Settlement."
- "Split Bill" screen: three modes — Even split (by N), By seat (uses Guest Slots already created in Phase 4), By item drag-and-drop into payer buckets.
- Per-bucket tender chooser: Card / Cash / Apple Pay / Comp / House Account.
- Backend creates one `Payment` record per bucket, all linked to the Session; "Close Table" gated on `sum(payments) >= session.total`.
- WS event `PaymentRecorded` updates admin's running-bill currency badge in real time.

---

## Scenario 8 — Tip handling (cash vs card vs service charge)

**Spec says:** Nothing. The word "tip" doesn't appear in the doc.

**Gap:** A waiter's entire livelihood, missing from the spec. Three real issues:
1. **Card tip**: needs to be capturable on the terminal and reconciled to the right waiter.
2. **Cash tip**: needs a manual "Tip received: $X cash" entry for the nightly tip-out report.
3. **Auto service charge** (common in EU and for parties of 6+): needs to be a per-session toggle with the % and "included" label on the printed receipt.
4. **Pool vs individual**: many restaurants pool tips by section or by shift; the system should know which model the restaurant uses.

**Concrete fix:**
- Add `tip_amount`, `tip_method` (card/cash), `service_charge_amount` to Payment. Add `tip_pool` config on Restaurant (`none | section | shift`).
- End-of-shift "Tip Report" screen for the waiter: today's card tips (system-known), today's cash tips (waiter-entered), service-charge share. Sign-off required, audit-logged.
- Admin Analytics: Tip-per-cover and Tip-vs-comp ratios.

---

## Scenario 9 — Allergy chain of custody

**Spec says:** Feature 5 AC2: "Upon modal opening, input focus defaults instantly to the 'Comment' text field." Allergies are free-text in the same comment box as "no onions."

**Gap:** "No onions" is a preference. "Allergic to nuts" is a *legal liability event*. Putting them in the same free-text field means:
- A line cook reading 30 tickets in a rush blends the two.
- No way to highlight the allergy on the KDS (no red banner, no audio cue).
- No way to flag it on the Session so it persists across re-orders / refires.
- No way to surface it on the printed kitchen ticket.

**Concrete fix:**
- Promote allergies to first-class: a structured `allergies` field on the Guest Slot (`nuts | shellfish | dairy | gluten | eggs | soy | other(free-text)`), entered once and inherited by every item ordered by that seat.
- Modifier Modal shows a sticky red banner if the Guest Slot has any allergy: "Seat 3: NUT ALLERGY" before submission.
- KDS renders allergy-flagged tickets with a red border, an audio chime distinct from new-ticket chime, and the allergy in bold on the item card.
- Backend: a soft-blocking check — if a menu item's `contains: [nuts]` matches a Guest Slot's allergy, the Modifier Modal forces the waiter to confirm with a typed "I have confirmed with kitchen" before Send.

---

## Scenario 10 — Walk-in too big for the table

**Spec says:** Phase 4 step 1: "Waiter taps an Occupied/Free table, selects the guest count..." No capacity check. No reseat workflow.

**Gap:** I seat a party of 5 at a 4-top because it's all I have. 10 minutes later T-08 (a 6-top) clears. I want to move them. There's no reseat flow — closing T-04 erases their order, and there's no way to migrate the active session.

**Concrete fix:**
- Hard validation: selecting a guest count > table capacity prompts "Seat anyway? (over capacity by 1)" — choosing yes flags the session for the manager.
- "Move Table" action on the Table Detail Overlay: pick target table from a list of Free tables with `capacity >= party_size`. Session migrates atomically; KDS in-flight tickets re-stamp with the new table ID; both old and new tables fire WS updates.
- Floor plan animation: the table chip "flies" from old to new position so the runner doesn't deliver to the wrong spot.

---

## Scenario 11 — Multiple "ready" pulses during rush

**Spec says:** Phase 3 (Atomic Tap) and Phase 3 of Kitchen (Global Batch View Sync). Multiple "Ready for Pickup" alerts fire simultaneously.

**Gap:** Four greens at once with one sidebar list is a visual flood. The waiter has to mentally pick the closest table or the oldest ticket. There's no triage heuristic, no "expedite this one — temperature-sensitive" badge, no run-list view.

**Concrete fix:**
- "Pickup Queue" screen: a sortable list of Ready dishes across all my tables, with columns: Table, Seat, Item, Ready-for (seconds), Temperature class (Hot/Cold/Tepid), Distance hint (from current location based on last-tapped table).
- Auto-prioritize Hot food: if a Hot item has been Ready > 60s, the row pulses red.
- One "Mark Picked Up" tap per row; aggregates into a "Run" so multiple tables in the same direction batch into one trip.
- Pulse alerts coalesce: if 4 Greens fire within 5s, the sidebar shows one expandable group "4 dishes ready — view queue".

---

## Scenario 12 — Modifier ambiguity ("Medium rare, extra sauce on the side")

**Spec says:** Feature 5: Modifier Modal with a Comment text field. AC2 says focus defaults to comment.

**Gap:** Free-text comments are line-cook roulette. "Medium rare" is a structured doneness; "extra sauce on the side" is a structured side-mod; jamming both into a comment box means the cook either misses one or asks the expo "what does this mean?" mid-rush. There's also no menu-item-level definition of available modifiers (a steak should have a Doneness picker; a salad should not).

**Concrete fix:**
- Menu Item schema gains `modifier_groups`: e.g., Steak has `Doneness` (required, one-of: Rare/Med Rare/Med/Med Well/Well), `Sauce` (multi-select), `Sides` (radio).
- Modifier Modal renders the groups as structured controls *above* the free-text comment.
- Comments are reserved for genuinely unstructured asks ("guest is allergic" — but see scenario 9 for the right field).
- KDS prints structured modifiers in bold next to the item name; free-text in italic below.

---

## Scenario 13 — Auto-fire vs Approve & Fire

**Spec says:** Phase 3: "taps Approve & Fire (or the system auto-fires, based on restaurant configuration)."

**Gap:** Two unanswered questions:
1. Who configures it — the Admin globally? Per-section? Per shift? The spec only says "restaurant configuration."
2. Even with auto-fire on, the waiter sometimes needs to hold (e.g., guest just paid online but is still parking the car — fire when seated, not on payment). No "Hold prepaid order" button is described.

**Concrete fix:**
- Move the auto-fire flag to a per-restaurant config in Admin → Settings → Service Flow, with an override per-Session toggle "Auto-fire prepaid: ON/OFF" visible to the waiter.
- On the prepaid order pulse, the table card shows a 30-second countdown "Auto-firing in 0:28 — tap to Hold." Tap Hold and it sits in the Waiter's "Held Orders" tray until Fire is pressed.

---

## Scenario 14 — Lost / dropped tablet

**Spec says:** Feature 1 AC3: role change invalidates token. Feature 12 AC1: WS drop shows a banner. Feature 2 AC3: reconnect replays missed events.

**Gap:** What's missing:
- No "this tablet just went offline / picked up by someone else" lock. If I drop the tablet and a guest picks it up, they have my session and can void/comp.
- No fast re-login. JWT spec says "valid JWT," but no PIN-based quick unlock for waiters — Google OAuth is fine for clients, terrible for staff who need to swap tablets between sections.
- No draft order persistence guarantee. If I had a 12-item draft at T-09 and the tablet dies, the spec doesn't promise the draft survives.

**Concrete fix:**
- Drafts auto-saved server-side every change (every Modifier Modal Submit). Reopening the table on a new tablet restores the draft byte-for-byte.
- Staff login: device-bound PIN (6 digits) on top of an admin-issued device token. Auto-lock after 60s of inactivity.
- "Tablet Lost" action in Admin: invalidates the device token, forces a fresh login, fires a WS event so the missing tablet (if found) shows a wipe screen.
- Per-action audit log: who-did-what-from-which-device, so a comped item is traceable to a specific staff PIN even on a shared tablet.

---

## Top improvements (prioritized)

| # | Improvement | Where | Priority | Why |
|---|---|---|---|---|
| 1 | **Waiter section assignment + section-scoped WS events** | New `ShiftAssignment` model; filter on Live Occupancy floor plan; toggle "Show full floor". | **H** | Without it, every notification is noise to everyone, or worse, owned by no one. Single biggest service-failure risk. |
| 2 | **First-class allergy field on Guest Slot + KDS red-banner rendering** | Promote out of free-text Comment in Modifier Modal; add `allergies` enum on Guest Slot; KDS distinct chime & red border. | **H** | Legal liability + guest safety. Cheap to build, catastrophic if missed. |
| 3 | **End-to-end Settlement screen (split bill, mixed tender, tip capture)** | New Phase 6 "Settlement" in Waiter Workflow with Split modes, Payment buckets, Tip fields. | **H** | Spec ends at "bill is paid" with no UI for paying. Without this, there is no shift. |
| 4 | **Cook-initiated 86 with retroactive impact modal on Waiter** | "Mark 86" button on Kitchen Kanban item; blocking modal on Waiter listing affected drafts & in-flight tickets with one-tap resolutions. | **H** | Removes Admin as bottleneck; prevents "I just took 3 salmon orders" embarrassment. |
| 5 | **Course pacing: `course` + `fire_when` on OrderItem + Kitchen HELD column** | Course picker in Modifier Modal; "Fire Course 2" button on table view; new KDS column. | **H** | Without it, cold mains land on top of half-eaten apps, every single ticket. |
| 6 | **Waiter-initiated Void Request + separate Comp action** | New "Request Void" button on item card; Manager approval queue; Comp as distinct flow with its own reason codes. | **H** | Admin-only voids will throttle every service recovery on a busy night. |
| 7 | **Merged-table (TableGroup) support** | Long-press multi-select on map → Merge; single Session across multiple tables; dotted-hull rendering; KDS ticket header "T-04+05". | **M** | Happens every weekend; current model can't represent it at all. |
| 8 | **Shift handover: per-Session notes, open-tasks checklist, Reassign Waiter** | Table Detail Overlay tab "Handover"; "Reassign Waiter" action; pre-shift "Inherited Tables" dashboard. | **M** | Eliminates the 10pm context loss. Quick to ship, high real-world value. |
| 9 | **Structured modifiers (modifier_groups) instead of comment-only** | Menu Item schema additions; Modifier Modal structured controls above Comment field; KDS bold rendering. | **M** | Reduces line-cook ambiguity dramatically; comments become exceptional, not the default. |
| 10 | **Pickup Queue + alert coalescing for rush triage** | New screen with sortable Ready-dish list, hot/cold class, age timer, "Run" grouping; sidebar coalesces simultaneous Greens. | **M** | Performance under load. Will become urgent the first weekend the kitchen actually keeps up. |

Tablet resiliency (server-side draft autosave, PIN re-login, Tablet Lost action) ranks **L** only because Feature 12 already covers WS drops and Feature 1 covers role-change token invalidation — the gaps here are real but smaller than the ten above.
