# Phase 0 Research: AI Guest Assistant

Resolves the design unknowns identified at the end of planning exploration. Each section records the decision and the concrete reuse points discovered in the codebase.

## R1 — Execution-layer split ("LLM proposes, app disposes")

**Decision**: The backend assistant API is the execution layer. The customer frontend holds the guest's JWT for its own authenticated requests (send message, confirm/reject proposal, hand-off) but never receives raw tool proposals to execute and never receives model credentials.

**Rationale**:
- The model's only output is a structured tool-call proposal. A server-side execution layer validates it against the strict schema (FR-018) and executes through the same service functions the normal UI buttons call (FR-005).
- The guest's authenticated identity is already established server-side by the JWT, so execution under that identity needs no token passing (SC-009).
- Client-side execution was rejected: it would require shipping the tool schemas and execution logic into the web app, duplicating safety rails (confirmation, audit, role bounds) and weakening NFR-006.
- Enforcement of "regardless of what the assistant says" (FR-015, US-6/SC-3) is trivial: the backend checks ownership + business rules at dispatch time, never trusting the model's prose.

**Flow** (guest message → reply/proposal):

```
frontend --WS event--> ... chat UI
frontend --POST messages/ (JWT)--> api/v1/views.py
  -> services.pipeline.ingest_message()
      1. rate-cap check (Redis)            [FR-023]
      2. persist user Message               [FR-012]
      3. enqueue celery task assistant_process_turn   [async tool calling]
        -> worker: services.router.categorize() -> focused tool set (FR-020)
        -> worker: services.ollama.generate() -> strict JSON output
        -> worker: schema validate (DRF serializers) [FR-018]
        -> worker: reply text           -> persist assistant Message
                                        -> broadcast ASSISTANT_MESSAGE
        -> worker: write-tool proposal  -> services.proposals.create()
                                        -> broadcast ASSISTANT_ACTION_PROPOSED
frontend --confirmation dialogue "The assistant wants to <action>. Approve?"
  -> POST proposals/{id}/confirm/ (JWT)
      -> validate pending/not-expired/owner (FR-024)
      -> re-validate business state at execution time (FR-006)
      -> execute via existing service      [FR-005]
      -> write ToolCall audit record       [FR-010]
      -> broadcast ASSISTANT_ACTION_RESULT (post-commit only, C4/FR-013)
```

## R2 — Async processing model

**Decision**: Message ingestion is asynchronous (Celery). `POST .../messages/` returns 202 after persisting the user message; the model turn runs in a worker; the reply/proposal is delivered as a WS event. Confirmation endpoints (`confirm/`, `reject/`) are synchronous REST because they mutate state through existing atomic services and the guest is already waiting.

**Rationale**:
- Matches the user's stated "agentic with async tool calling" intent and keeps a slow local-model inference from blocking the web request worker.
- Re-prompt/retry on malformed output (FR-018) and follow-up turns after reject/dismiss (Checkpoint Rule) are naturally queued.
- The 5 s reply NFR-002 is still met: a small local model on a single turn is well under budget; the queue keeps concurrency bounded.

**Idempotency / replay**:
- The unit of idempotency is the ToolProposal (`proposal_id`, FR-013/SC-006): only a `pending → confirmed` transition executes, guarded by an atomic conditional update on `(conversation, proposal_id, status=pending)`. A duplicated `confirm` returns the already-recorded result without re-execution.
- WS replay: on reconnect the client re-fetches `GET .../messages/` + active proposal state before enabling writes (Offline & Reconnection Contract).

## R3 — Tool catalog and intent router (FR-020)

**Decision**: Intent router with four outcomes — `info`, `booking`, `cart`, `none` (plain chat). Each intent offers a focused set of ≤ 5 tools; read-only tools execute silently and are summarized; write tools always require the confirmation checkpoint (FR-019).

| Intent | Offered tools (per turn) | Tool nature |
|--------|--------------------------|-------------|
| `info` | `get_menu`, `get_restaurant_info`, `check_availability` | all read-only |
| `booking` | `check_availability`, `create_reservation`, `reschedule_reservation`, `cancel_reservation` | 1 read + 3 write |
| `cart` | `get_menu`, `add_to_cart` | 1 read + 1 write |
| `none` | (no tools) | plain reply / clarifying question / hand-off offer |

- `check_availability` is shared across `info` and `booking`; the router narrows the surface before the model picks (FR-020).
- Intent routing is deterministic (keyword + entity matching in `services/router.py`), not model-driven, so tool exposure stays cheap and predictable.
- Extension mechanism (FR-014/FR-015): tools self-register in `services/registry.py` with (name, JSON schema, executor, `needs_confirmation`). Personas are a named set of allowed tools; a persona's access is bound to the acting role at dispatch. Adding a tool/persona requires no changes to existing assistants (US-6).

## R4 — Ollama integration (greenfield)

**Decision**: New `httpx` dependency; a small async client in `services/ollama.py` calls the Ollama REST API (`POST {OLLAMA_URL}/api/chat`) with `format: "json"` (structured output / JSON mode) and a system prompt that enumerates only the current turn's tool set plus UI context (FR-021). Response is parsed as JSON and validated with DRF serializers (reuse codebase idiom; no new schema library).

**Settings** (`core/settings/base.py`):
- `ASSISTANT_OLLAMA_URL` — default `http://llm-service:11434` (docker) / `http://localhost:11434` (local dev via env)
- `ASSISTANT_OLLAMA_MODEL` — configurable, e.g. `qwen2.5:7b`; no hard-coded model
- `ASSISTANT_PROPOSAL_TTL_SECONDS` — `300` (FR-024)

**Failure handling**:
- Malformed / out-of-schema output → reject, re-prompt once (FR-018), then fall back to a courteous "I couldn't process that" message + hand-off offer; no execution.
- Ollama unreachable / timeout → fallback message + hand-off offer; no model inference cost on capped messages (FR-023).

## R5 — Observability and audit

**Decision**: Every turn logs structured fields: `conversation_id`, `intent`, `tools_offered`, `model_latency_ms`, `schema_rejects`, `outcome`. Every tool execution writes a `ToolCall` audit row (FR-010): acting guest, channel, tool, inputs, outcome, reference id, timestamps. Retention: ToolCall 30 days, Conversation (cascade: Messages, ToolProposals, HandoffRequests) 7 days (FR-022). Cleanup enforced by a daily Celery beat task `assistant_cleanup` plus lazy expiry of stale proposals at confirm time (FR-024).

## R6 — Rate limiting (FR-023)

**Decision**: Redis-backed counters keyed on the guest's authenticated identity (user pk, else `guest_id`/cart-session claim): `assistant:cap:{identity}:hour:{yyyyMMddHH}` and `assistant:cap:{identity}:day:{yyyyMMdd}`. Checked first in `services/pipeline.ingest_message()` before any model inference; a hit returns the friendly limit notice (HTTP 429 with `retry_after`). Limits configured via settings (`ASSISTANT_HOURLY_CAP`, `ASSISTANT_DAILY_CAP`).

## R7 — Reuse points discovered in the codebase

- **Reservations**: `apps/reservations/services.py`, `apps/reservations/selectors.py` — availability checks, overlapping-range validation, business-hours/capacity rules; `create/update/cancel` entry points for tools. `Reservation.status` (`pending/active/completed/cancelled`) governs lifecycle; `type` (`pre_booked/walk_in`) unchanged.
- **Cart**: `apps/orders/services/cart.py`, `apps/orders/services/sessions.py`, `apps/orders/services/walk_in.py` (public API re-exported via `__all__`), `apps/orders/models/cart_session.py`, `apps/orders/models/cart_item.py` — `CartSession` (reservation FK, status active/closed, participants M2M), `CartItem`. `add_to_cart` tool reuses the same add-item path as `apps/orders/api/v1/` (mounted at `.../cart/sessions/...`). Closed-session rule is enforced by the service (US-3/AS-5).
- **Menu**: `apps/menu/models/__init__.py` + `apps/menu/models/translations.py` — `Menu`, `MenuCategory`, `MenuItem` (price `Decimal(14,4)`, `is_available`, M2M ingredients/allergens), translations with default-locale fallback. `get_menu` tool reads here; public-read endpoints already exist (FR-016 exception pattern).
- **Restaurant**: `RestaurantSettings` for opening hours / business rules read by `get_restaurant_info` and `check_availability`.
- **Notifications / WS**: `common/channels.py` (auth + group helpers), `common/notification_store.py` + `common/notification_events.py` (Redis-backed store, TTL), staff groups `staff_<restaurant_id>`. Hand-off pushes a staff notification through this stream (FR-011).
- **Identity**: JWT (simplejwt); tokens may carry user identity or `guest_id`/cart-session claims (anonymous guest flow). Assistant identity = user pk, else guest/cart-session claim; ownership enforced on conversation/proposal.
- **Config/infra**: `core/settings/{base,local,production}.py`, `core/celery.py` (broker + beat), `core/routing.py` (Channels — note: routing currently loads `production` while `manage.py` uses `local`; the assistant consumer is added to the same routing module, and this mismatch should be revisited when wiring the consumer).

## R8 — Open items deferred to Phase 2 (tasks)

- Exact Ollama model tag + structured-output confirmation for the chosen model (NFR-007 baseline).
- Concrete cap defaults per setting (local vs production).
- Pagination/timestamps for message history replay.
