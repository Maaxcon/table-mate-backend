# Assistant Event Contracts (WebSocket)

Transport: `wss://<host>/ws/assistant/<conversation_id>/` — the authenticated guest's conversation group `assistant_conversation_<conversation_id>`.

- **Delivery guarantee**: at-least-once (constitution baseline).
- **Replay**: on reconnect the client refreshes via `GET .../messages/` + `GET .../conversations/{id}/` (`pending_proposal`) before enabling writes.
- **schema_version**: `1`; additive-only forward compatibility — clients **ignore** unsupported versions rather than crash.
- **No tokens are ever present** in any event payload.

All payloads share envelope:

```json
{ "type": "<EVENT_TYPE>", "schema_version": 1, "data": { ... } }
```

---

## `ASSISTANT_MESSAGE`

Delivered when the model produced a conversational reply (no tool call).

- **Audience**: the authenticated guest of the conversation (session-scoped)
- **When**: after the assistant Message row is persisted (post-turn)

```json
{
  "type": "ASSISTANT_MESSAGE",
  "schema_version": 1,
  "data": {
    "message_id": "m_<uuid>",
    "role": "assistant",
    "text": "The risotto contains gluten (flour-based stock). Would you like a gluten-free alternative?",
    "created_at": "2026-08-05T10:01:00Z"
  }
}
```

---

## `ASSISTANT_ACTION_PROPOSED`

Delivered when the model proposed a state-changing tool call. The client renders the confirmation dialogue.

- **Audience**: the authenticated guest of the conversation (session-scoped)
- **When**: after the ToolProposal row is persisted

```json
{
  "type": "ASSISTANT_ACTION_PROPOSED",
  "schema_version": 1,
  "data": {
    "proposal_id": "p_<uuid>",
    "tool": "create_reservation",
    "summary": "Create a reservation for 4 guests on 2026-08-06 at 19:00",
    "consequence": "This books a table for 4 at 19:00 on 2026-08-06. You can reschedule or cancel it later.",
    "expires_at": "2026-08-05T10:06:00Z"
  }
}
```

- `expires_at` = creation + 5 minutes (FR-024). The client shows a countdown and disables confirm past it.

---

## `ASSISTANT_ACTION_RESULT`

Delivered after a confirmed proposal executes — **only after the backend transaction commits** (No-Optimistic-Truth Rule).

- **Audience**: the authenticated guest of the conversation (session-scoped)

```json
// success
{
  "type": "ASSISTANT_ACTION_RESULT",
  "schema_version": 1,
  "data": {
    "proposal_id": "p_<uuid>",
    "tool": "create_reservation",
    "outcome": "success",
    "reference_id": "res_<uuid>"
  }
}
```

```json
// business failure at execution time (FR-006)
{
  "type": "ASSISTANT_ACTION_RESULT",
  "schema_version": 1,
  "data": {
    "proposal_id": "p_<uuid>",
    "tool": "create_reservation",
    "outcome": "failed",
    "reference_id": null
  }
}
```

- On failure the assistant follows up with alternatives (FR-007) via a subsequent `ASSISTANT_MESSAGE`.
- A duplicated delivery of the same result does not re-execute (idempotency keyed on `proposal_id`, SC-006).

---

## Error / edge events

- **Proposal expired/dismissed**: no `ASSISTANT_ACTION_RESULT`; the assistant follows up with an `ASSISTANT_MESSAGE` re-proposing against current state (FR-024, Checkpoint Rule).
- **Rate cap**: not an event — the sending request is rejected with HTTP 429 before any model work.

## Audience note (C1)

Events target exactly the guest conversation group. Staff receive hand-off notifications through the **existing** staff notification stream (`staff_<restaurant_id>`), not through these assistant events.
