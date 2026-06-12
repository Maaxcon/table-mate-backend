# Tasks: Real-Time Multiplayer Shared Cart

**Input**: Design documents from `specs/019-realtime-shared-cart/`
**Prerequisites**: plan.md (required), spec.md (required)

**Tests**: Required for realtime, role-based access, and transactional integrity.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- Include exact file paths in descriptions

---

## Phase 1: Foundational (WebSocket + Broadcast Layer)

**Purpose**: Core WebSocket consumer, broadcast helper, and service-layer wiring that the realtime feature depends on.

- [X] T001 [P] Create `CartConsumer` (AsyncWebsocketConsumer) in `apps/orders/consumers.py` — read-only, auth via JWT query param, group per session public_id
- [X] T002 [P] Create WebSocket routing in `apps/orders/routing.py` — path `ws/cart/<session_id>/` -> CartConsumer
- [X] T003 [P] Create broadcast helper `cart_group_send(session_id, event_type)` in `apps/orders/broadcast.py` — uses `async_to_sync(channel_layer.group_send)` for sync-service compatibility, emits `{"type": "cart_updated", "session_id": "..."}`
- [X] T004 [P] Add `transaction.on_commit()` calls to cart mutation services (`add_item_to_cart`, `remove_item_from_cart`, quantity update) in `apps/orders/services.py` — each calls `cart_group_send` inside `on_commit` to guarantee the DB write commits *before* the WebSocket broadcast fires. Emit once per transaction, not once per item (batch via service-level dedup when multiple items change in one commit).
- [X] T005 Update `core/routing.py` to include `apps.orders.routing.websocket_urlpatterns`
- [X] T006 [P] Create helper `cart_group_name(session_id: str) -> str` in `common/channels.py` alongside existing `hall_group_name`

**Checkpoint**: WebSocket infrastructure ready — CartConsumer accepts connections, cart mutations trigger `on_commit`-deferred broadcast.

---

## Phase 2: User Story 1 — Guests Add and See Items in Real Time (Priority: P1) 🎯 MVP

**Goal**: Two participants in the same cart session see each other's additions/deletions within 500ms via WebSocket broadcast.

**Independent Test**: Open two WS connections to `ws/cart/<session_id>/` with different participant tokens. POST a CartItem via REST for user A. User B's WS receives `{"type": "cart_updated"}`. GET confirms the item exists.

### Tests for User Story 1

- [ ] T007 [P] [US1] Contract test for CartItem PATCH endpoint in `tests/contract/test_orders_cart_api.py`
- [ ] T008 [P] [US1] Integration test: WebSocket receives event on CartItem create in `tests/integration/test_cart_websocket.py`
- [ ] T009 [P] [US1] Integration test: WebSocket receives event on CartItem delete in `tests/integration/test_cart_websocket.py`
- [ ] T010 [P] [US1] Integration test: WebSocket receives event on CartItem quantity update in `tests/integration/test_cart_websocket.py`
- [ ] T011 [P] [US1] Integration test: Unauthenticated WS connection is rejected (code 4001) in `tests/integration/test_cart_websocket.py`
- [ ] T012 [P] [US1] Integration test: Non-participant WS connection is rejected (code 4003) in `tests/integration/test_cart_websocket.py`

### Implementation for User Story 1

- [X] T013 [P] [US1] Add `update_cart_item_quantity` service in `apps/orders/services.py` with select_for_update
- [X] T014 [P] [US1] Create `UpdateCartItemSerializer` in `apps/orders/api/v1/serializers.py` for PATCH quantity
- [X] T015 [US1] Add `partial_update` action to `CartSessionItemViewSet` in `apps/orders/api/v1/views.py` for PATCH
- [X] T016 [US1] Add PATCH route to `apps/orders/api/v1/urls.py`

**Checkpoint**: Real-time sync works — CartItem CRUD via REST triggers WebSocket broadcast to all participants.

---

## Phase 3: User Story 2 — Concurrent Operations with Race Condition Protection (Priority: P1)

**Goal**: Simultaneous add/delete/update operations on the same cart item use row-level locks, preventing data corruption.

**Independent Test**: Fire two concurrent POST requests with the same menu_item to the same session. Exactly one CartItem exists with combined quantity.

### Tests for User Story 2

- [ ] T017 [P] [US2] Integration test: Concurrent adds to same menu_item produce combined quantity in `tests/integration/test_cart_concurrent.py`
- [ ] T018 [P] [US2] Integration test: Concurrent delete + update results in one winning (404 or 200) in `tests/integration/test_cart_concurrent.py`
- [ ] T019 [P] [US2] Integration test: Adding unavailable menu_item returns 400 in `tests/contract/test_orders_cart_api.py`

### Implementation for User Story 2

- [X] T020 [US2] Add `select_for_update()` locking to `add_item_to_cart` and `remove_item_from_cart` services in `apps/orders/services.py`
- [X] T021 [US2] Add `is_available` check for menu_item before adding in `apps/orders/services.py`

**Checkpoint**: Race conditions handled — no duplicate or corrupted CartItem state under concurrent access.

---

## Phase 4: User Story 3 — WebSocket Reconnection and State Recovery (Priority: P2)

**Goal**: On WS reconnect, the client (or server) ensures no missed updates — the client re-fetches cart state via REST.

**Independent Test**: Disconnect a WS client, make a cart change via REST for another user, reconnect the WS client, verify it receives a `cart_updated` event (or triggers re-fetch).

### Tests for User Story 3

- [ ] T022 [P] [US3] Integration test: WS disconnect + reconnect + cart change -> event received in `tests/integration/test_cart_websocket.py`

### Implementation for User Story 3

- [X] T023 [US3] Add reconnect event in `CartConsumer.connect()` to send `cart_updated` on join in `apps/orders/consumers.py`

**Checkpoint**: Reconnection recovery works — no missed updates after disconnect.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Schema updates, security check, lint, final verification.

- [X] T024 [P] Run `drf-spectacular` schema generation and verify cart endpoints appear in `api/schema/`
- [X] T025 Run `ruff` lint check and fix any issues
- [X] T026 Run `bandit` security check and fix any issues
- [X] T027 Run full test suite: `pytest`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Foundational)**: Must complete before phases 2-4
- **Phase 2 (US1)**: Depends on Phase 1 completion
- **Phase 3 (US2)**: Depends on Phase 1 completion; can run in parallel with Phase 2
- **Phase 4 (US3)**: Depends on Phase 2 completion (needs CartConsumer)
- **Phase 5 (Polish)**: Depends on Phases 2-4

### Parallel Opportunities

- T001 through T006 can all run in parallel (different files)
- T007 through T012 (US1 tests) can run in parallel
- T013, T014 are independent and can run in parallel
- US1 and US2 work can proceed in parallel after Phase 1
- T017, T018, T019 (US2 tests) can run in parallel

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: WebSocket + Broadcast Layer
2. Complete Phase 2: US1 (Real-time sync)
3. **STOP and VALIDATE**: Two participants see each other's changes in real time
4. Deploy/demo if ready

### Incremental Delivery

1. Phase 1 → WebSocket ready
2. Phase 2 → Real-time sync working → **MVP!**
3. Phase 3 → Race condition protection
4. Phase 4 → Reconnection recovery
5. Phase 5 → Polish
