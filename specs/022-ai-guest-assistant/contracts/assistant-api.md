# Assistant REST API Contract

Base path: `/api/assistant/` — all endpoints require a valid JWT (`IsAuthenticated`). Identity = authenticated user pk, or the `guest_id`/cart-session claim for guest tokens.

## Endpoints

### `POST /api/assistant/conversations/`

Start (or resume) a conversation.

```json
// request
{ "language": "en" }   // optional; defaults to restaurant default language
```

```json
// 201 Created
{
  "conversation_id": "c_<uuid>",
  "status": "active",
  "language": "en",
  "created_at": "2026-08-05T10:00:00Z"
}
```

- Returns the existing conversation when the guest already has one for the restaurant (partial-unique per owner), else creates it.
- Errors: `401` unauthenticated.

### `GET /api/assistant/conversations/{conversation_id}/`

Fetch a conversation (owner only).

```json
// 200 OK
{
  "conversation_id": "c_<uuid>",
  "status": "active",
  "language": "en",
  "recent_messages": [
    { "message_id": "m_<uuid>", "role": "user", "text": "book a table for 4 tonight at 7", "created_at": "..." },
    { "message_id": "m_<uuid>", "role": "assistant", "text": "I can help with that.", "created_at": "..." }
  ],
  "pending_proposal": null
}
```

- `pending_proposal` carries the active (unexpired) proposal, if any (see `POST proposals/{id}/confirm/`).
- Errors: `401`, `403` (not owner), `404`.

### `POST /api/assistant/conversations/{conversation_id}/messages/`

Send a guest message. Enqueues the model turn; reply arrives as a WS event.

```json
// request
{
  "text": "does the risotto contain gluten?",
  "ui_context": { "active_view": "menu", "menu_category_id": "cat_<uuid>", "cart_item_count": 3 }
}
```

```json
// 202 Accepted
{ "message_id": "m_<uuid>", "conversation_id": "c_<uuid>" }
```

- `ui_context` is optional and validated as a JSON object; appended to the prompt for deictic references (FR-021).
- Rate caps enforced before enqueue (FR-023): on cap hit → `429`:

```json
{ "detail": "You have reached the hourly assistant message limit. Please try again later.", "retry_after": 1800 }
```

- No model inference is spent on capped messages.
- Errors: `400` (empty text, malformed `ui_context`), `401`, `403` (not owner), `404`, `429`.

### `GET /api/assistant/conversations/{conversation_id}/messages/`

History for replay (owner only). Paginated by `created_at`; newest-last ordering is stable for the reconnect replay window.

```json
// 200 OK
{
  "next": null,
  "results": [
    { "message_id": "m_<uuid>", "role": "assistant", "text": "...", "created_at": "..." }
  ]
}
```

- Errors: `401`, `403`, `404`.

### `POST /api/assistant/proposals/{proposal_id}/confirm/`

Confirm and execute a pending tool proposal. The confirmation dialogue "The assistant wants to `<action>`. Approve?" is rendered by the client; this endpoint is the only path to execution.

```json
// request
{}   // no body required (idempotency keyed on proposal_id)
```

```json
// 200 OK — success
{
  "proposal_id": "p_<uuid>",
  "tool": "create_reservation",
  "outcome": "success",
  "reference_id": "res_<uuid>"
}
```

```json
// 200 OK — executed but business validation failed at run time (FR-006)
{
  "proposal_id": "p_<uuid>",
  "tool": "create_reservation",
  "outcome": "failed",
  "error_code": "slot_taken"
}
```

- Re-validates availability/context at execution time (FR-006) before dispatching to the existing service (FR-005); audit row written in the same transaction (FR-010).
- Success is only reported after the backend transaction commits (No-Optimistic-Truth Rule).
- Duplicate confirm of the same `proposal_id` returns the recorded result without re-executing (idempotency, SC-006).
- Errors: `401`, `403` (not owner), `404`; `409` with `{ "detail": "proposal_expired" }` or `{ "detail": "proposal_already_processed" }`.

### `POST /api/assistant/proposals/{proposal_id}/reject/`

Dismiss a pending proposal (outside-tap or explicit cancel). Marks `rejected` and enqueues a follow-up assistant turn.

```json
// 200 OK
{ "proposal_id": "p_<uuid>", "status": "rejected" }
```

- Never executes. Errors: `401`, `403`, `404`.

### `POST /api/assistant/conversations/{conversation_id}/handoff/`

Request an async staff hand-off (FR-011). Records context, notifies staff via the existing stream, tells the guest staff will follow up.

```json
// request
{ "reason": "I need help with a dietary requirement" }
```

```json
// 201 Created
{ "handoff_id": "h_<uuid>", "status": "open", "notified_at": "2026-08-05T10:05:00Z" }
```

- Errors: `401`, `403`, `404`.

## Status Code Summary

| Code | Meaning |
|------|---------|
| 200 | success / already-processed result |
| 201 | created (conversation, hand-off) |
| 202 | accepted (message enqueued) |
| 400 | malformed request (empty text, bad JSON body, out-of-schema `ui_context`) |
| 401 | unauthenticated |
| 403 | authenticated but not owner / out of role |
| 404 | unknown resource |
| 409 | proposal not in `pending` state (expired / rejected / already processed) |
| 429 | rate cap reached (with `retry_after`) |

## OpenAPI

All schemas are declared with drf-spectacular and reflected in the committed `schema.yaml` snapshot; contract tests assert the snapshot stays in sync.
