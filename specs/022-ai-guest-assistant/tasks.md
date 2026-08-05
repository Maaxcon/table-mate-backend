# Tasks: AI Guest Assistant

**Input**: Design documents from `/specs/022-ai-guest-assistant/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/ (assistant-api.md, events.md, tools.md), quickstart.md

**Tests**: Test tasks are REQUIRED for this feature — the constitution mandates verification for role-based access, realtime (WebSocket) event contracts, replay/version handling, transactional/atomic data behavior, and destructive-action confirmation, all of which are in scope (see constitution Compliance "Tasks artifacts MUST include verification for role enforcement, websocket replay/version handling, ... and atomic data behavior when relevant").

**Scope note**: This repository is the backend. The spec's Frontend Surface Contract (chat widget mounting, offline write-blocking, confirmation dialogue rendering) is consumed by the customer web app repo; the backend deliverables here are the REST + WS contracts and their tests.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Django apps live under `apps/` (e.g. `apps/assistant/`), core wiring in `core/`, tests under `tests/` at repository root. No `src/` prefix.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Create `apps/assistant/` app skeleton (`__init__.py`, `apps.py` with `AssistantConfig`) and register `apps.assistant` in `INSTALLED_APPS` in `core/settings/base.py`; add `httpx` to dependencies in `pyproject.toml` and lock with `uv lock`
- [ ] T002 [P] Add `ASSISTANT_OLLAMA_URL` (default `http://llm-service:11434`), `ASSISTANT_OLLAMA_MODEL`, `ASSISTANT_PROPOSAL_TTL_SECONDS` (300), `ASSISTANT_HOURLY_CAP`, `ASSISTANT_DAILY_CAP` to `core/settings/base.py`
- [ ] T003 [P] Register `assistant_cleanup` daily Celery beat schedule in `core/celery.py` (confirm `app.autodiscover_tasks` picks up `apps.assistant.tasks`)
- [ ] T004 [P] Wire REST URLs in `core/urls.py` (`path("api/assistant/", include("apps.assistant.api.v1.urls"))`) and WS consumer route in `core/routing.py` (`ws/assistant/<uuid:conversation_id>/` → `apps.assistant.consumers.AssistantConsumer`); document the existing `core/routing.py` loading `production` settings while `manage.py` uses `local` (see research.md R7)
- [ ] T005 [P] Scaffold `apps/assistant/api/v1/` (`__init__.py`, `urls.py`, `serializers.py`, `views.py`) and `tests/assistant/` directory

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T006 Create assistant models — `Conversation`, `Message`, `ToolProposal`, `ToolCall`, `HandoffRequest` — in `apps/assistant/models.py` per `data-model.md` (partial unique index on pending `ToolProposal` per conversation, user XOR guest_key check, conversation→ToolCall `SET_NULL`, retention-safe FK semantics) + migration in `apps/assistant/migrations/`
- [ ] T007 Implement selectors for conversations, messages, proposals, and handoffs in `apps/assistant/selectors.py` (scoped by owner identity + restaurant)
- [ ] T008 Implement conversation service (`get_or_create`, ownership enforcement, language defaulting) in `apps/assistant/services/conversations.py`
- [ ] T009 Implement `ToolRegistry` (name → schema/executor/needs_confirmation) and persona→tool-set binding in `apps/assistant/services/registry.py` (FR-014/FR-015 seam)
- [ ] T010 Implement deterministic intent router (`info`/`booking`/`cart`/`none`) that returns the focused ≤5-tool set per turn in `apps/assistant/services/router.py` (FR-020)
- [ ] T011 Implement Ollama client in `apps/assistant/services/ollama.py`: httpx async POST to `{ASSISTANT_OLLAMA_URL}/api/chat` with `format: "json"`, system prompt enumerating current tool set + injected `ui_context` (FR-021), strict JSON parse, DRF-serializer schema validation (FR-018), single re-prompt on malformed output then courteous fallback + hand-off offer
- [ ] T012 Implement message pipeline in `apps/assistant/services/pipeline.py`: Redis-backed hourly/daily rate-cap counters keyed on owner identity (FR-023, 429 with `retry_after`), persist user `Message`, enqueue `assistant_process_turn`
- [ ] T013 Implement Celery tasks in `apps/assistant/tasks.py`: `assistant_process_turn` (router → ollama → persist/broadcast), `assistant_followup` (post-reject follow-up), `assistant_cleanup` (delete conversations >7 d, ToolCall >30 d, expire stale proposals — FR-022/FR-024)
- [ ] T014 Implement WS consumer in `apps/assistant/consumers.py`: join `assistant_conversation_<conversation_id>` group, typed/versioned event builders (`ASSISTANT_MESSAGE`, `ASSISTANT_ACTION_PROPOSED`, `ASSISTANT_ACTION_RESULT`, `schema_version: 1`), at-least-once delivery + reconnect replay source (C4, FR-013)
- [ ] T015 Implement REST conversations + messages endpoints in `apps/assistant/api/v1/views.py` + `serializers.py`: `POST conversations/`, `GET conversations/{id}/` (with `pending_proposal`), `POST conversations/{id}/messages/` (202 + enqueue), `GET conversations/{id}/messages/` (history/replay); all `IsAuthenticated` with ownership checks
- [ ] T016 [P] Contract test for conversations/messages REST API in `tests/assistant/test_conversations.py` (201/202/400/401/403/404, ownership, history replay shape)
- [ ] T017 [P] Pipeline test in `tests/assistant/test_pipeline.py` (hourly/daily caps → 429 no inference, malformed input, enqueue happens)
- [ ] T018 [P] Ollama client test (mocked `httpx`/Ollama) in `tests/assistant/test_ollama_client.py` (valid JSON accepted, out-of-schema rejected + re-prompt, unreachable → fallback, no credentials in prompt)
- [ ] T019 [P] Router test in `tests/assistant/test_router.py` (each intent yields the focused tool set; tool set ≤5; `none` yields no tools)
- [ ] T020 [P] WS event contract test in `tests/assistant/test_events.py` (payload/schema_version correctness, unknown-version ignore, replay window, at-least-once/idempotency assumptions)

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Guest Asks Questions and Gets Accurate Answers (Priority: P1) 🎯 MVP

**Goal**: Guest chats and receives answers built from the restaurant's live menu, allergen, ingredient, price, opening-hours, and reservation-policy data (FR-002), with read-only tools executed silently and summarized (FR-019).

**Independent Test**: Send prepared questions (menu, gluten/allergens, hours after an update, reservation policy) through the chat; answers match current DB state and no staff escalation is needed (SC-003); requests for another guest's or staff-only data are refused with no leak (SC-005).

### Implementation for User Story 1

- [ ] T021 [P] [US1] Implement `get_menu` executor (search + translations fallback, price/availability/allergens/ingredients) in `apps/assistant/services/tools.py`
- [ ] T022 [P] [US1] Implement `get_restaurant_info` executor (hours/address/policy/contact; `payment` → staff referral, no financial data) in `apps/assistant/services/tools.py`
- [ ] T023 [P] [US1] Implement `check_availability` executor (reuse reservation availability selectors; nearest alternatives when taken/outside hours — FR-007) in `apps/assistant/services/tools.py`
- [ ] T024 [US1] Wire read-only silent execution into `assistant_process_turn` in `apps/assistant/tasks.py` (run tool, inject result back into prompt, summarize via `ASSISTANT_MESSAGE`) for the `info` intent
- [ ] T025 [US1] Integration test for US1 in `tests/assistant/test_tools.py` (menu/allergen/hours/policy answers against live data, data-boundary refusal SC-005, tool result summarization)

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Guest Books a Table Through the Assistant (Priority: P1)

**Goal**: Guest requests a booking; assistant checks availability, proposes it, guest confirms in the dialogue, and the reservation is created through the same rules as a manual booking (FR-005/FR-006).

**Independent Test**: Complete request → proposal → confirm entirely in the chat; verify a reservation appears in the guest's list, respects business hours/capacity, requires confirmation (SC-001/SC-004), rejects after 5-min expiry (SC-013), and never duplicates on retry (SC-006).

### Implementation for User Story 2

- [ ] T026 [P] [US2] Implement proposals service in `apps/assistant/services/proposals.py`: `create` (summary/consequence/5-min `expires_at`, FR-024), `confirm` (atomic `pending→confirmed` transition keyed on `proposal_id`, re-validate at execution time FR-006, dispatch), `reject` (enqueue `assistant_followup`), lazy expiry
- [ ] T027 [P] [US2] Implement `create_reservation` executor (party_size/date/time/notes; on confirm re-check availability then reuse reservation service) in `apps/assistant/services/tools.py`
- [ ] T028 [US2] Implement proposal `confirm`/`reject` REST endpoints in `apps/assistant/api/v1/views.py` + `serializers.py` (200 result / 409 expired-or-processed / 403 not-owner; idempotent duplicate confirm returns recorded result)
- [ ] T029 [US2] Emit `ASSISTANT_ACTION_PROPOSED` (post-create) and `ASSISTANT_ACTION_RESULT` (post-commit only — No-Optimistic-Truth Rule) in `apps/assistant/services/proposals.py` + `consumers.py`
- [ ] T030 [US2] Write `ToolCall` audit record (actor, channel, tool, inputs, outcome, reference_id, timestamps) in the same transaction as execution in `apps/assistant/services/proposals.py` (FR-010)
- [ ] T031 [US2] Test booking flow in `tests/assistant/test_proposals.py` (SC-001 end-to-end, slot-taken-between-proposal-and-confirm → `slot_taken` + alternatives, expiry SC-013, duplicate-confirm idempotency SC-006, audit trail SC-004)

**Checkpoint**: At this point, User Story 2 should be fully functional and testable independently

---

## Phase 5: User Story 3 - Guest Adds Items to Their Cart Through the Assistant (Priority: P1)

**Goal**: Guest asks to add dishes; assistant proposes item + price + required modifiers, guest confirms, and items are added to the active cart via the existing cart service (FR-005).

**Independent Test**: Ask to add a dish with modifiers, confirm, and verify the cart line appears with correct quantity/price (SC-002); unavailable dishes are not added; closed carts are refused.

### Implementation for User Story 3

- [ ] T032 [P] [US3] Implement `add_to_cart` executor (menu_item_id, quantity, modifiers, guest slot/comment; re-check `is_available` + active cart at execution) in `apps/assistant/services/tools.py`
- [ ] T033 [US3] Integrate `cart` intent: expose `get_menu` + `add_to_cart`, and drive modifier clarification before proposing when required modifiers are missing (US-3/AS-4) in `apps/assistant/services/router.py` + `tools.py`
- [ ] T034 [US3] Test cart flow in `tests/assistant/test_tools.py` (SC-002 add-with-modifiers, unavailable item → alternatives, missing modifier → ask before propose, closed cart → `cart_closed`)

**Checkpoint**: At this point, User Story 3 should be fully functional and testable independently

---

## Phase 6: User Story 4 - Guest Modifies or Cancels a Reservation Through the Assistant (Priority: P2)

**Goal**: Guest moves or cancels their own reservation via proposal → confirmation, re-checking availability, under the same rules as manual changes, with cancellation requiring explicit consequence display.

**Independent Test**: Reschedule and cancel a reservation through the chat, verifying each requires confirmation, the freed slot is reusable, and the audit shows the destructive action was confirmed (SC-004).

### Implementation for User Story 4

- [ ] T035 [P] [US4] Implement `reschedule_reservation` executor (date/time/party_size; re-check availability at confirm; not-owner/`reservation_not_found` guards) in `apps/assistant/services/tools.py`
- [ ] T036 [P] [US4] Implement `cancel_reservation` executor with destructive-action confirmation (proposal `consequence` MUST name the exact reservation being cancelled — Destructive Action Confirmation Contract) in `apps/assistant/services/tools.py`
- [ ] T037 [US4] Test modify/cancel in `tests/assistant/test_proposals.py` (reschedule + slot freed, cancel requires consequence + confirm, conflict → valid alternative, `already_cancelled` guard)

**Checkpoint**: At this point, User Story 4 should be fully functional and testable independently

---

## Phase 7: User Story 5 - Guest Hands Off to Human Staff (Priority: P2)

**Goal**: When the assistant can't answer or the guest wants a human, record a hand-off with conversation context, notify staff via the existing notification stream, and tell the guest staff will follow up (FR-011).

**Independent Test**: Request a human in chat; verify a `HandoffRequest` with context is recorded and a staff notification lands on the `staff_<restaurant_id>` stream (SC-008); payment requests are referred to staff, never processed (FR-009).

### Implementation for User Story 5

- [ ] T038 [P] [US5] Implement handoff service in `apps/assistant/services/handoff.py` (record `HandoffRequest` with `context_summary`, mark `notified_at`)
- [ ] T039 [US5] Implement `POST conversations/{id}/handoff/` endpoint in `apps/assistant/api/v1/views.py` + `serializers.py` (201 + `handoff_id`)
- [ ] T040 [US5] Push staff notification via `staff_<restaurant_id>` group + Redis notification store (reuse `common/notification_store.py`/`channels.py`) in `apps/assistant/services/handoff.py` (FR-011, constitution XII)
- [ ] T041 [US5] Test hand-off in `tests/assistant/test_handoff.py` (SC-008 record + notification, guest keeps chatting after hand-off, payment referral FR-009)

**Checkpoint**: At this point, User Story 5 should be fully functional and testable independently

---

## Phase 8: User Story 6 - Assistant Is Extended with New Tools and an Admin Persona (Priority: P3)

**Goal**: New tools and personas are additive: registry-driven discovery, persona tool access bound to the acting role, enforced server-side regardless of model output (FR-014/FR-015).

**Independent Test**: Register a new tool and an `admin` persona; verify they appear without touching existing assistants, and a guest requesting an admin-only tool is denied server-side (SC-007).

### Implementation for User Story 6

- [ ] T042 [P] [US6] Make tool discovery data-driven: `ToolRegistry` auto-discovers registered tools, intent router reads category→tool mapping from the registry in `apps/assistant/services/registry.py` + `router.py`
- [ ] T043 [US6] Add `admin` persona demo bound to the `admin` role (role-bounded tool set) with cross-persona denial at dispatch in `apps/assistant/services/registry.py` + `services/proposals.py` (FR-015)
- [ ] T044 [US6] Test extension mechanism in `tests/assistant/test_registry.py` (add tool/persona without touching existing assistants — SC-007; guest persona denied admin-only tool regardless of model output)

**Checkpoint**: At this point, User Story 6 should be fully functional and testable independently

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T045 [P] Retention verification: `assistant_cleanup` deletes conversations >7 d and `ToolCall` >30 d and expires stale proposals; add `tests/assistant/test_cleanup.py` (SC-011, FR-022/FR-024)
- [ ] T046 [P] Security hardening: run `bandit -r apps/assistant`, confirm no secrets/credentials ever reach the prompt or model payload, sanitize/truncate stored payloads in `apps/assistant/services/ollama.py`
- [ ] T047 [P] OpenAPI drift gate: regenerate `schema.yaml` (drf-spectacular) and confirm the diff contains only additive assistant endpoints; update committed snapshot
- [ ] T048 Run `quickstart.md` validation (US-1..US-6 acceptance scenarios + SC-001..SC-013) and record results
- [ ] T049 Run full quality gates: `ruff check apps/assistant tests/assistant`, `mypy`, `bandit`, `pip-audit`, `pytest tests/assistant -q`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational - no dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational - depends on US1 only in the sense that read-only tools (`get_menu`, `check_availability`) already exist for availability checks, but must remain independently testable
- **User Story 3 (P1)**: Can start after Foundational - reuses the proposal mechanism built in US2 (proposals service is shared write-tool infra created in US2); independently testable once US2 proposal endpoints exist
- **User Story 4 (P2)**: Depends on US2 proposal mechanism + confirm/reject endpoints
- **User Story 5 (P2)**: Can start after Foundational - independent of US2/3/4
- **User Story 6 (P3)**: Depends on Foundational registry + router; demo persona builds on the tool infra from US1-4

### Within Each User Story

- Models before services
- Services before endpoints
- Core implementation before integration
- Story complete before moving to next priority
- Tests (where included) are written in the story phase and MUST pass before the story checkpoint

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (T016-T020 after T006-T015 wiring exists)
- Once Foundational completes: US1, US2, US5 can start in parallel (independent); US3/US4 join once US2's proposal endpoints land; US6 after registry/tools mature
- Within US1: T021-T023 run in parallel, then T024 (integration), then T025 (test)
- Within US2: T026-T027 in parallel, then T028-T030 (sequential wiring), then T031
- Within US4: T035-T036 in parallel, then T037
- Within US5: T038 in parallel with nothing else in the story; T039-T040 sequential, then T041

---

## Parallel Example: User Story 1

```bash
# Launch all read-only tool executors together:
Task: "Implement get_menu executor in apps/assistant/services/tools.py"
Task: "Implement get_restaurant_info executor in apps/assistant/services/tools.py"
Task: "Implement check_availability executor in apps/assistant/services/tools.py"
```

## Parallel Example: User Story 2

```bash
# Launch proposal infra + booking executor together:
Task: "Implement proposals service in apps/assistant/services/proposals.py"
Task: "Implement create_reservation executor in apps/assistant/services/tools.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (conversational answers from live data)
4. **STOP and VALIDATE**: Test User Story 1 independently (T025, SC-003)
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 (booking, P1) → Test independently → Deploy/Demo
4. Add User Story 3 (cart, P1) → Test independently → Deploy/Demo
5. Add User Story 4 (modify/cancel, P2) → Test independently → Deploy/Demo
6. Add User Story 5 (hand-off, P2) → Test independently → Deploy/Demo
7. Add User Story 6 (extension, P3) → Test independently → Deploy/Demo
8. Polish & quality gates (Phase 9) before PR

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1
   - Developer B: User Story 2 (proposals infra, unblocks US3/US4)
   - Developer C: User Story 5
3. After US2 proposal endpoints: Developer A/B/C pick up US3/US4/US6

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verification tasks for role enforcement (T016, T044), websocket event contracts + unknown-version handling (T020), at-least-once delivery + replay (T020), atomic data behavior (T031/T034/T037), and destructive-action confirmation (T036/T037) are REQUIRED by the constitution and included above
- Webhook/payment path: N/A for this feature (FR-009 payment referral only; T022 covers the referral)
- Frontend offline UX + confirmation-dialogue rendering are consumed in the customer web app repo against these contracts; no frontend build tasks live in this repo
- Commit after each task or logical group; verify tests fail before implementing where a test is written ahead of implementation
- Stop at any checkpoint to validate the story independently
- Avoid: vague tasks, same-file conflicts, cross-story dependencies that break independence
