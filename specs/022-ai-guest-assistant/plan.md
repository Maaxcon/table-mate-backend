# Implementation Plan: AI Guest Assistant

**Branch**: `feat/041-AI-guest-assistant` | **Date**: 2026-08-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/022-ai-guest-assistant/spec.md`

## Summary

Build an in-app AI guest assistant for the restaurant customer web app. A guest chats through a realtime widget; the backend routes each message to a locally hosted LLM (Ollama `llm-service`, already in docker-compose) with strict structured output. The model is a pure reasoning layer: it either produces a conversational reply or proposes one tool call from a small, intent-routed catalog (3-5 tools per turn). The **backend assistant API is the execution layer** (plan decision for the split left open by the spec's Assumptions): the model never holds credentials and never calls the backend; proposals are schema-validated, stored with a 5-minute expiry, surfaced to the guest as a confirmation dialogue, and only then executed by reusing the existing reservation/cart/menu services under the guest's authenticated identity. All actions are audited; conversations are deleted after 7 days and audit records after 30 days; per-guest hourly/daily caps are enforced in Redis; staff hand-off is recorded and pushed over the existing notification stream.

The design follows the "LLM proposes, app disposes" architecture (FR-017/FR-018/FR-019/FR-020/FR-021) and is built so future assistants (e.g., a staff admin assistant) plug in additively via a tool registry and persona-scoped tool sets (FR-014/FR-015, US-6).

The customer web app consumes the REST + WS contracts: it renders the chat widget, the confirmation dialogue (summary + consequence, expiry countdown, dismiss-notify), offline write-blocking with reconnect replay, and the hand-off UX. Those frontend deliverables are tracked as Phase 10 in tasks.md and implemented in the customer web app repo on the same feature branch (constitution C-I).

## Technical Context

**Language/Version**: Python 3.12, Django 5, DRF
**Primary Dependencies**: django-channels/daphne (existing), celery + redis (existing, configured), `httpx` (new — async client for the Ollama REST API), drf-spectacular (existing). Ollama runs in docker-compose at `llm-service:11434` (container network) / `localhost:11434` (host dev).
**Storage**: PostgreSQL (new entities: Conversation, Message, ToolProposal, ToolCall, HandoffRequest), Redis (assistant WS channel layers, rate-cap counters, Celery broker).
**Testing**: pytest with top-level `tests/` (contract + integration), ruff lint, bandit security scan, mypy, committed `schema.yaml` OpenAPI snapshot (drf-spectacular).
**Target Platform**: Backend REST + WebSocket services for the customer web app.
**Project Type**: Web service (Django/DRF single project).
**Performance Goals**: Assistant reply delivered within 5 s under normal load (NFR-002); full booking conversation within 2 minutes (NFR-001); 2+ concurrent conversations per active guest session (NFR-003).
**Constraints**: Model has no credentials/network (FR-017); proposals expire in 5 min (FR-024); per-guest hourly/daily caps (FR-023); retention 7 d/30 d (FR-022); live events WS-only, REST create/mutate-only (constitution C4); at-least-once delivery + idempotency keyed on `proposal_id` (FR-013, C5); read-only tools silent, write tools always confirmed (FR-019).
**Scale/Scope**: Single fast local model; one pending proposal per conversation; per-restaurant tenancy via `RestaurantScopedModel` convention; no payment handling.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Rule | Status | Evidence in Plan |
|------|------|--------|------------------|
| C1 | Right role, right moment, zero ambiguity is preserved | PASS | Assistant events target the exact guest conversation group (`assistant_conversation_<id>`); replies use live backend data (FR-002/FR-006), UI context injected for deictic references (FR-021); ambiguous input triggers clarifying questions (FR-016). |
| C2 | Canonical shared entity contracts are preserved (Restaurant/Table/Order/OrderItem/Ticket/Session/Staff) | PASS | Zero shape changes to Reservation/CartSession/CartItem/Menu/MenuItem; tools call existing services (FR-005); only new additive entities (Conversation/Message/ToolProposal/ToolCall/HandoffRequest). |
| C3 | Role access matrix is backend-enforced and structurally reflected in clients | PASS | `IsAuthenticated` on all endpoints; ownership checks on conversation/proposal; tools run under the caller's identity; admin-tool/persona set is role-bounded at execution (FR-015); denied regardless of model output. |
| C4 | Live state uses WebSocket-only typed/versioned events; REST is create/mutate only | PASS | `ASSISTANT_MESSAGE`/`ASSISTANT_ACTION_PROPOSED`/`ASSISTANT_ACTION_RESULT` WS-only, `schema_version: 1`, unknown versions ignored; REST endpoints create/mutate only (send message, confirm/reject, handoff). |
| C5 | Delivery guarantee supports at-least-once semantics and reconnect replay | PASS | At-least-once delivery per constitution baseline; reconnect replay window from persisted Message history; execution idempotent via `proposal_id` key (FR-013, SC-006). |
| C6 | Payment confirmation is webhook-only with signature validation | N/A | Assistant never handles payments (FR-009); refers guests to staff. |
| C7 | Void flow is atomic with explicit rollback and audit data | N/A | No void flow; cart/reservation changes reuse existing atomic service transactions (spec Transaction & State Authority). |
| C8 | Session lifecycle is explicit (open triggers, human close, immutable snapshot) | PASS | No parallel occupancy model; tool-created reservations follow the existing lifecycle; analytics still source from reservation/session records (Session Lifecycle Rules). |
| C9 | Kitchen queue ordering preserves injection-time priority | N/A | Assistant does not touch the kitchen queue. |
| C10 | Auth uses role-scoped tokens with immediate invalidation on role change | PASS | Reuses existing JWT; assistant scoped by token identity (user pk or `guest_id`/cart-session claim); execution authorized under that identity. |
| C11 | Floor layout updates are immutable/versioned with stable table IDs and backend-driven delivery | N/A | No floor-plan surface. |
| C12 | Financial records are externally read-only; AVG PREP is query-time from raw cycle data | N/A | Assistant does not write financial records. |
| C13 | Frontend-only constraints are respected when frontend scope exists (role trees, offline error state, destructive confirmations, floor plan <=100ms paint) | PASS | Widget mounts only in customer role tree; offline blocks send/confirm with reconnect replay; destructive confirmations for all state-changing proposals (Checkpoint Rule). |
| C14 | Mandatory backend stack and architecture are respected (Python/Django/DRF/PostgreSQL/Redis/Channels + Skinny Views/Fat Services/Selectors) | PASS | New `apps/assistant` with skinny `api/v1/views.py`, fat `services/` package, `selectors.py`; Django/DRF/PostgreSQL/Redis/Channels/Celery throughout. |

## Project Structure

### Documentation (this feature)

```text
specs/022-ai-guest-assistant/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── README.md
│   ├── assistant-api.md
│   ├── tools.md
│   └── events.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/assistant/
├── __init__.py
├── apps.py
├── models.py            # Conversation, Message, ToolProposal, ToolCall, HandoffRequest
├── selectors.py         # conversation/message/proposal/handoff selectors
├── services/
│   ├── __init__.py
│   ├── conversations.py # get-or-create, close, ownership enforcement
│   ├── pipeline.py      # ingest: rate cap -> persist user msg -> enqueue Celery turn
│   ├── router.py        # intent router (info|booking|cart|none) -> focused tool set
│   ├── registry.py      # ToolRegistry: name -> schema/executor/needs_confirmation (FR-014/15)
│   ├── tools.py         # tool executors reusing reservations/orders/menu services
│   ├── ollama.py        # httpx client, prompt builder, structured-output parse, retry
│   ├── proposals.py     # create/confirm/reject/expire, dispatch, idempotency
│   └── handoff.py       # handoff record + staff notification
├── consumers.py         # AssistantConsumer (guest WS), conversation group
├── tasks.py             # Celery: assistant_process_turn, assistant_followup, assistant_cleanup
├── api/
│   └── v1/
│       ├── __init__.py
│       ├── serializers.py
│       ├── views.py
│       └── urls.py
└── migrations/

core/
├── urls.py              # include apps/assistant.api.v1.urls under api/assistant/
├── routing.py           # include ws/assistant/<uuid:conversation_id>/ consumer
├── settings/base.py     # INSTALLED_APPS, ASSISTANT_OLLAMA_* settings, CELERY_BEAT_SCHEDULE
└── celery.py            # beat import for assistant_cleanup

tests/
└── assistant/
    ├── test_conversations.py
    ├── test_pipeline.py        # caps, malformed input, enqueue
    ├── test_router.py          # intent -> tool set selection
    ├── test_tools.py           # executor read/write + business-rule reuse + data boundaries
    ├── test_proposals.py       # confirm/reject/expiry/idempotency
    ├── test_events.py          # WS payloads, schema_version, replay
    ├── test_handoff.py         # handoff record + staff notification
    └── test_ollama_client.py   # structured-output validation, retry, fallback (mocked)
```

**Structure Decision**: Single Django project. The assistant is a new Django app `apps/assistant` following the existing per-domain app layout (`apps/reservations`, `apps/orders`, `apps/menu`, ...) with the Skinny Views/Fat Services/Selectors pattern. It is wired into the existing router layers (`core/urls.py`, `core/routing.py`) and configuration (`core/settings/base.py`, `core/celery.py`). The customer web app (frontend) consumes the REST + WS contracts; it is NOT given raw tool proposals to execute. Rationale: keeping the model-proposal → validation → execution path entirely server-side makes the "app disposes" guarantee (SC-009/SC-010) enforceable and testable, avoids shipping tool schemas + execution logic to the client, and keeps FR-005 (same services/business rules) trivially true.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations (all gates PASS or N/A). No complexity justification needed.
