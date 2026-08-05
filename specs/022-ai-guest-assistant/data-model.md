# Phase 1 Data Model: AI Guest Assistant

Five new entities in `apps/assistant/models.py`, all inheriting the project's `common.models.BaseModel` (`UUIDMixin`, `TimestampMixin`). Four are restaurant-scoped via the `RestaurantScopedModel` convention (adds `restaurant` FK + `public_id`); `ToolCall` is restaurant-scoped but intentionally decoupled from `Conversation` so the 30-day audit trail survives conversation deletion (7-day retention).

## Entity Overview

| Entity | Retention | Key identity | Purpose |
|--------|-----------|--------------|---------|
| `Conversation` | 7 d (deleted) | owner (user XOR guest_key) + restaurant | persistent chat session |
| `Message` | 7 d (cascade) | conversation + role | persisted turn history / replay |
| `ToolProposal` | 7 d (cascade); effective 5-min validity | conversation + status | pending action awaiting confirmation; idempotency unit |
| `ToolCall` | 30 d (deleted) | restaurant + proposal | audit trail of executed tools |
| `HandoffRequest` | 7 d (cascade) | conversation + restaurant | async staff hand-off |

Identity model: a guest is either an authenticated customer (`user` FK) or a JWT guest-token identity (`guest_key` string, e.g. `guest:{guest_id}` / cart-session id). Exactly one of the two is set (checked in `clean()` + DB constraint).

---

## `Conversation`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID pk | |
| `public_id` | UUID | exposed to API; from `RestaurantScopedModel` |
| `restaurant` | FK `restaurants.Restaurant` | PROTECT (scoped model) |
| `user` | FK auth.User, **null** | set iff owner is a registered customer |
| `guest_key` | CharField, **blank** | set iff owner is a guest token |
| `status` | CharField | `active` / `closed` |
| `language` | CharField | conversation language (default restaurant default) |
| `created_at` / `updated_at` | timestamp | |

**Constraints / indexes**
- DB CHECK: `user` XOR `guest_key` non-empty (exactly one owner identity).
- Unique: `(restaurant, user)` where user NOT NULL; `(restaurant, guest_key)` where guest_key NOT NULL (partial unique indexes) — one active conversation per guest per restaurant.
- Index: `(restaurant, updated_at)`.

**Rules**
- Open: created by `services.conversations.get_or_create()` on first message; never auto-closed by the assistant.
- Close: not part of US-1..6; status reserved for cleanup/admin (future). Cleanup deletes rows regardless of status after 7 d.

---

## `Message`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID pk | |
| `conversation` | FK `Conversation` | CASCADE (deleted with conversation) |
| `role` | CharField | `user` / `assistant` |
| `text` | TextField | |
| `created_at` | timestamp | |

**Constraints / indexes**
- Index: `(conversation, created_at)` for ordered history / replay.

**Rules**
- Assistant messages that carry a proposal or result reference the proposal via `ToolProposal.message` (see below); `Message` itself stays clean.
- Ordering by `created_at` (+ pk tiebreak) is stable for replay (FR-012, Offline & Reconnection).

---

## `ToolProposal`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID pk | |
| `public_id` | UUID | the `proposal_id` used in confirm/reject URLs and WS payloads; **idempotency key** |
| `conversation` | FK `Conversation` | CASCADE |
| `message` | FK `Message`, **null** | the assistant message that issued the proposal |
| `user` | FK auth.User, **null** | proposer identity (with `guest_key`) — mirrors Conversation owner; used for ownership check |
| `guest_key` | CharField, **blank** | guest-token identity |
| `tool` | CharField | one of the registered tool names (e.g. `create_reservation`, `add_to_cart`) |
| `parameters` | JSONField | validated tool inputs (strict schema, FR-018) |
| `summary` | TextField | human-readable action shown in the confirmation dialogue |
| `consequence` | TextField | human-readable consequence (e.g. "This cancels your reservation #… for 4 guests on …") |
| `status` | CharField | `pending` / `confirmed` / `rejected` / `expired` / `executed` |
| `expires_at` | DateTimeField | created_at + 5 min (FR-024) |
| `created_at` / `updated_at` | timestamp | |

**Constraints / indexes**
- Partial unique index: `(conversation_id)` **WHERE `status = 'pending'`** — at most one pending proposal per conversation (keeps the confirmation dialogue unambiguous).
- DB CHECK: `user` XOR `guest_key` (mirror of Conversation).
- Index: `(conversation, status)`.

**Rules**
- Creation: only write-tools (FR-019) — created after schema validation and expiry stamping.
- Confirm: guarded atomic transition `pending → confirmed` keyed on `(public_id, status='pending')`; anything else returns the already-recorded result (idempotency, SC-006) or 409 for rejected/expired.
- Expiry: `expires_at` checked at confirm time (lazy) and by the daily cleanup task (FR-024); expired → `expired`, no execution, assistant re-proposes.
- Reject/dismiss: `pending → rejected`; enqueues a follow-up assistant turn (Checkpoint Rule "notify the assistant so it can follow up").

---

## `ToolCall` (Action Record)

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID pk | |
| `restaurant` | FK `restaurants.Restaurant` | PROTECT (scoped) |
| `conversation` | FK `Conversation`, **SET_NULL** | survives conversation deletion (audit retention 30 d > conversation 7 d) |
| `proposal` | FK `ToolProposal`, **SET_NULL** | the confirmed proposal (write tools) |
| `user` | FK auth.User, **null** | acting guest |
| `guest_key` | CharField, **blank** | acting guest-token identity |
| `channel` | CharField | `assistant` (this feature) — FR-010 channel field |
| `tool` | CharField | executed tool name |
| `parameters` | JSONField | inputs as executed |
| `outcome` | CharField | `success` / `failed` |
| `error_code` | CharField, **blank** | e.g. `slot_taken`, `cart_closed`, `item_unavailable`, `proposal_expired`, `not_owner` |
| `reference_id` | CharField, **blank** | created/changed entity public_id (reservation / cart session) |
| `executed_at` | DateTimeField | auto_now_add |

**Constraints / indexes**
- Index: `(restaurant, executed_at)` for admin audit review (Admin role).
- Index: `(proposal_id)`.

**Rules**
- One `ToolCall` per confirmed proposal at most (idempotency): created inside the same transaction as the state change; the transition guard on `ToolProposal` prevents duplicates.
- Written after the backend transaction commits (No-Optimistic-Truth Rule): `ASSISTANT_ACTION_RESULT` fires only post-commit.

---

## `HandoffRequest`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID pk | |
| `conversation` | FK `Conversation` | CASCADE |
| `restaurant` | FK `restaurants.Restaurant` | PROTECT |
| `status` | CharField | `open` / `resolved` |
| `context_summary` | TextField | captured conversation context attached to the hand-off (Waiter may view this context only) |
| `notes` | TextField, **blank** | guest/staff free text |
| `notified_at` | DateTimeField, **null** | set when the staff notification was pushed |
| `created_at` | timestamp | |

**Constraints / indexes**
- Index: `(restaurant, status, created_at)` for staff follow-up queueing.

**Rules**
- Created by `services.handoff.create()`; staff notified via `staff_<restaurant_id>` group + Redis notification store (FR-011). Guest keeps chatting until staff follow up (US-5/AS-4).
- No payment context is ever attached (FR-009).

---

## Field Conventions

- All JSON payloads (`parameters`, later `ui_context`) are JSON-encoded in `JSONField`.
- Timestamps are timezone-aware (project convention).
- All `user` FKs are `on_delete=PROTECT`? — No: per project convention user-optional fields use `SET_NULL`; conversation ownership uses CASCADE semantics documented per field above.
- Follow `common/models.py` `BaseModel` + `RestaurantScopedModel` exactly (same imports, same mixin order) as existing apps.

## Relationship Diagram (text)

```text
Conversation 1─N Message
Conversation 1─N ToolProposal 1─N(0..1) ToolCall
Conversation 1─N HandoffRequest
ToolProposal N─1 Message        (the issuing assistant message)
ToolCall N─1 ToolProposal       (SET_NULL on both conversation & proposal)
Restaurant 1─N Conversation / ToolCall / HandoffRequest
```

## Migrations

Single squashed migration per new app (project uses normal managed migrations). No changes to existing tables.
