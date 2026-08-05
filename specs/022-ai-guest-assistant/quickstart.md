# Quickstart: Validating the AI Guest Assistant

Manual + automated validation mapped to the spec's acceptance scenarios (US-1..6) and success criteria (SC-001..013). Run automated checks with the project's pytest suite (`tests/assistant/`); manual scenarios assume the local stack (docker compose: `web`, `db`, `redis`, `llm-service`) and a seeded restaurant with a published menu and `RestaurantSettings`.

## Prereqs

1. Pull a model: `docker compose exec llm-service ollama pull qwen2.5:7b` (or set `ASSISTANT_OLLAMA_MODEL`).
2. Ensure `core/routing.py` serves the assistant consumer (`ws/assistant/<conversation_id>/`) — note the existing `routing.py`/`settings` module mismatch and verify the local dev routing actually wires the consumer.
3. Authenticate as a guest/customer JWT in the customer app.

## US-1 — Answers from live data (SC-003, SC-005)

| # | Scenario | Steps | Pass |
|---|----------|-------|------|
| 1 | Gluten question matches current data | Ask "what dishes contain gluten"; verify list matches `MenuItem` allergen data | ☐ |
| 2 | Changed hours reflected | Update `RestaurantSettings` hours; ask "when are you open tomorrow"; verify new hours | ☐ |
| 3 | Unanswerable → fallback + hand-off offer | Ask an out-of-domain question; verify courteous "can't answer" + hand-off offered | ☐ |
| 4 | Data boundary | Ask about another guest's reservation / staff-only data; verify refusal + no data leak (test: `test_tools.py`) | ☐ |

## US-2 — Booking (SC-001, SC-004, SC-005, SC-009, SC-010, SC-013)

| # | Scenario | Steps | Pass |
|---|----------|-------|------|
| 1 | Propose + confirm | "book a table for 4 tomorrow at 19:00" → proposal event → confirm → reservation in guest's list | ☐ |
| 2 | No slot → alternatives | Request a full slot → nearest alternatives proposed, no booking until chosen + confirmed | ☐ |
| 3 | Outside business hours | Request 02:00 → constraint explained + in-hours alternatives (no auto-booking) | ☐ |
| 4 | Reject/abandon | Reject the proposal → no reservation created (`proposal_id` never executed) | ☐ |
| 5 | Slot taken between proposal and confirm | Take the slot manually, then confirm → outcome `failed`/`slot_taken`, no duplicate; alternatives proposed (SC-013 for the 5-min expiry: confirm an expired proposal → 409) | ☐ |
| 6 | Audit check | Verify a `ToolCall` row exists: actor, channel, tool, inputs, outcome, reference id, timestamps (SC-004) | ☐ |

## US-3 — Cart (SC-002, SC-005)

| # | Scenario | Steps | Pass |
|---|----------|-------|------|
| 1 | Add with modifiers | "add a medium risotto with extra mushrooms" → proposal with price + modifiers → confirm → cart shows correct quantity/price | ☐ |
| 2 | Unavailable item | Request a discontinued dish → not added, alternatives proposed | ☐ |
| 3 | Missing required modifier | Omit a required modifier → assistant asks before proposing | ☐ |
| 4 | Closed cart | Close the session, then ask → explained, item not added (`cart_closed`) | ☐ |

## US-4 — Modify / cancel (SC-004, SC-005)

| # | Scenario | Steps | Pass |
|---|----------|-------|------|
| 1 | Reschedule | "move my booking to 20:00" → availability re-checked → proposal → confirm → updated reservation | ☐ |
| 2 | Cancel | "cancel my booking" → consequence states the exact reservation → confirm → cancelled, slot freed | ☐ |
| 3 | Conflict | Modify into a conflicting slot → explained + valid alternative proposed | ☐ |

## US-5 — Hand-off (SC-008)

| # | Scenario | Steps | Pass |
|---|----------|-------|------|
| 1 | Request human | "I need a human" → `HandoffRequest` recorded with context; staff notified on `staff_<restaurant_id>` stream; guest told staff will follow up | ☐ |
| 2 | Payment referral | "pay with my card" → assistant refuses and refers to staff, no payment handled (FR-009) | ☐ |
| 3 | Staff offline | Hand-off with no staff online → recorded, guest informed follow-up is pending | ☐ |
| 4 | Keep chatting | After hand-off, further messages still answered | ☐ |

## US-6 — Extension (SC-007, FR-014/FR-015)

| # | Scenario | Steps | Pass |
|---|----------|-------|------|
| 1 | New tool additive | Register a new tool in `registry.py` → available to assistants with no changes to existing assistant code (automated: registry test) | ☐ |
| 2 | Admin persona (demo) | Register an `admin` persona bound to admin role → tools bounded by role | ☐ |
| 3 | Cross-persona denial | Guest persona requests an admin-only tool → denied server-side regardless of model output | ☐ |

## Cross-cutting (SC-006, SC-009, SC-010, SC-011, SC-012)

| SC | Check | Pass |
|----|-------|------|
| SC-006 | Duplicate `confirm` on the same `proposal_id` → same result, no duplicate reservation/cart line | ☐ |
| SC-009 | Model has no credentials/network; every execution routes through the authenticated backend path (test: no secret env in prompt assembly; audit shows actor) | ☐ |
| SC-010 | Malformed/out-of-schema proposal → zero executions (test: `test_ollama_client.py` with mocked malformed output) | ☐ |
| SC-011 | Freeze retention ages: conversation rows > 7 d and `ToolCall` rows > 30 d are gone after `assistant_cleanup` runs | ☐ |
| SC-012 | Exceed hourly cap → HTTP 429 friendly notice, no inference spent (test: pipeline cap check) | ☐ |

## Automated gate

```bash
ruff check apps/assistant tests/assistant
bandit -r apps/assistant
pytest tests/assistant -q
```

OpenAPI snapshot in sync: regenerate `schema.yaml` and diff (drf-spectacular).
