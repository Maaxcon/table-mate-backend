# Feature Specification: Real-Time Multiplayer Shared Cart

**Feature Branch**: `019-realtime-shared-cart`
**Created**: 2026-06-04
**Status**: Draft
**Input**: User description: Real-Time Multiplayer Shared Cart (REST + WebSocket Sync)

## User Scenarios & Testing

### User Story 1 - Guests Add and See Items in Real Time (Priority: P1)

Two guests sitting at the same table share a communal bill. When one guest adds an item (e.g., "Burger"), the other guest's device should show that item appear on the bill within 500ms without manual refresh.

**Why this priority**: This is the core value of the feature — enabling a shared, real-time ordering experience for table guests.

**Independent Test**: Can be fully tested by creating two authenticated clients bound to the same reservation/session, having one add a cart item, and verifying the other client receives a WebSocket event and can read the updated cart.

**Acceptance Scenarios**:

1. **Given** Guest A and Guest B are authenticated and connected to the same cart session via WebSocket, **When** Guest A adds a menu item, **Then** Guest B receives a `cart_updated` WebSocket event within 500ms.
2. **Given** Guest A and Guest B are in the same cart session, **When** Guest A deletes an item, **Then** Guest B receives a `cart_updated` WebSocket event.

---

### User Story 2 - Concurrent Add Operations with Race Condition Protection (Priority: P1)

Two guests tap "Add" on the same item at nearly the same millisecond. Only one OrderItem is created (quantity combined), and inventory is correctly debited once.

**Why this priority**: Race conditions during peak table activity could cause double-charging or incorrect inventory counts. This is critical for data integrity.

**Independent Test**: Can be tested by issuing two concurrent POST requests with the same menu item from different users and asserting only one CartItem exists with combined quantity.

**Acceptance Scenarios**:

1. **Given** two cart participants simultaneously POST the same menu item, **When** both requests are processed, **Then** exactly one CartItem record exists with quantity equal to the sum of both requests.
2. **Given** a menu item has `is_available=False`, **When** any participant tries to add it, **Then** the API returns a `400 Bad Request` with an error code, and the cart state is unchanged.

---

### User Story 3 - WebSocket Reconnection and State Recovery (Priority: P2)

A guest loses WiFi while adding items to the cart. When connectivity is restored, the WebSocket reconnects and the frontend automatically fetches the latest cart state to ensure no updates were missed.

**Why this priority**: Mobile guests frequently experience network drops. Without auto-recovery, the cart UI would show stale data, eroding trust in the shared bill.

**Independent Test**: Can be tested by disconnecting a WebSocket client (dropping connection), making a cart change via REST, then having the client reconnect and verifying it emits a `cart_updated` event or triggers a re-fetch.

**Acceptance Scenarios**:

1. **Given** a guest's WebSocket disconnects, **When** another guest adds an item, **Then** upon reconnection the guest receives a `cart_updated` event or automatically re-fetches the cart, showing the correct state.
2. **Given** a guest's WebSocket was disconnected for an extended period, **When** they reconnect, **Then** they see the full current cart state (no gaps).

---

### User Story 4 - Interaction Guards on Closed Sessions (Priority: P2)

Once a cart session is closed (e.g., the bill is submitted to the kitchen), no participant can add or remove items.

**Why this priority**: Prevents accidental or malicious changes after the order is in production, ensuring restaurant operations are not disrupted.

**Independent Test**: Can be tested by setting a CartSession status to `closed` and asserting that all mutation endpoints return `409 Conflict`.

**Acceptance Scenarios**:

1. **Given** a closed CartSession, **When** any participant attempts to add an item, **Then** the API returns `409 Conflict` with error code `cart_session_closed`.
2. **Given** a closed CartSession, **When** any participant attempts to delete an item, **Then** the API returns `409 Conflict` with error code `cart_session_closed`.

---

### Edge Cases

- **The "Sold Out" Race**: If two users try to add the last available item simultaneously, one succeeds and the other receives a `400 Bad Request`. The failing user's UI shows a toast and reverts any optimistic render.
- **The "Delete War"**: If User A deletes an item while User B updates its quantity, database transaction locks ensure one action completes first. If User A's delete wins, User B's update receives a `404 Not Found`.
- **Non-participant Intrusion**: An authenticated user who is not a participant of the reservation cannot see or modify the cart; API returns `403 Forbidden` or `404 Not Found`.
- **Simultaneous Quantity Update**: If two users update the same item's quantity concurrently, the final value equals the result of whichever transaction commits last.

## Requirements

### Functional Requirements

- **FR-001**: Authenticated users who are participants of the same reservation MUST be able to create a shared cart session.
- **FR-002**: Cart participants MUST be able to add menu items to the shared cart.
- **FR-003**: Cart participants MUST be able to remove items from the shared cart.
- **FR-004**: Cart participants MUST be able to update item quantities in the shared cart.
- **FR-005**: Adding a menu item that is not available MUST return a clear error and leave the cart unchanged.
- **FR-006**: When a cart item is created, updated, or deleted, a WebSocket event MUST be broadcast to all connected participants.
- **FR-007**: The WebSocket consumer MUST be read-only — it ignores all incoming client messages.
- **FR-008**: The WebSocket connection MUST require JWT authentication via query parameter, rejecting unauthenticated connections with code 4001.
- **FR-009**: Non-participants MUST be prevented from reading or mutating the cart (403 Forbidden or 404 Not Found).
- **FR-010**: Mutations on a closed/archived cart session MUST return `409 Conflict`.
- **FR-011**: Concurrent add operations on the same menu item MUST use row-level locks to prevent duplicate record creation and data corruption.
- **FR-012**: The WebSocket broadcast payload MUST include the event type (`cart_updated`) and should be lightweight — the client should re-fetch the full cart via REST after receiving the event.
- **FR-013**: On WebSocket reconnect, the frontend MUST automatically fetch the latest cart state via REST.
- **FR-014**: The frontend MUST display which user added each cart item (using `added_by` or equivalent field).
- **FR-015**: The API schema MUST be documented with `drf-spectacular`.
- **FR-016**: The cart item REST endpoints MUST use `select_for_update` on the session and menu item to prevent race conditions.

### Canonical Contract Impact

- **Impacted Entities**: CartSession, CartItem
- **Contract Delta**: No field changes to existing models. WebSocket event payload schema is additive.
- **Backend Source of Truth Rule**: All state mutations go through REST with transaction locking. WebSocket layer is read-only notification only.

### Role Access Matrix

- **Customer**: Create cart session (as participant), add items, remove items, update quantities, view cart, receive WebSocket events. Denied: mutating closed sessions, accessing non-participant carts.
- **Waiter**: View any cart session in their restaurant. Denied: adding/removing items to guest carts (managed by guests).
- **Admin**: Same as waiter, full read access. Denied: mutating guest carts without explicit need.
- **Cook**: No cart access.

### Realtime Event Contracts

- **Event**: `cart_updated`
- **Audience**: All participants of the cart session
- **Transport**: WebSocket channel per session (`ws/cart/<session_id>/`)
- **Payload**: `{ "type": "cart_updated", "session_id": "<uuid>" }`
- **schema_version**: `1` — initial version, backward compatible.
- **Unknown Version Handling**: Client applies the standard re-fetch behavior regardless of schema version.

### Event Delivery Guarantees

- **Delivery Guarantee**: At-least-once. The channel layer delivers the event to all group members; if a member is offline, delivery is skipped (no persistent queue for disconnected clients).
- **Replay Window**: On reconnect, the client re-fetches the full cart via REST, effectively replaying all missed events.
- **Idempotency Strategy**: Events are informational (tell clients to re-fetch). The GET endpoint is idempotent, so duplicate delivery causes no harm.

### Transaction & State Authority

- **Authoritative Transition**: Cart item add/remove/update via REST API.
- **Atomic Group**: CartItem create/update/delete + WebSocket broadcast. Both succeed or the transaction rolls back.
- **Broadcast Timing**: WebSocket emit is deferred via `transaction.on_commit()` inside the service layer. This ensures the broadcast only fires *after* the enclosing `transaction.atomic()` block commits. Since per-request `ATOMIC_REQUESTS` is off, the service's explicit `atomic()` block is required for `on_commit` to defer; a bare `on_commit` outside a transaction would fire immediately and provide no protection.
- **Rollback Rule**: If the database write fails (integrity, lock timeout), `on_commit` callbacks are discarded automatically — the WebSocket broadcast is skipped.
- **Emit Once Per Commit**: The service layer batches the broadcast — if multiple CartItems are affected in a single commit, one `cart_updated` event is emitted rather than one per item.
- **No-Optimistic-Truth Rule**: Client-side optimistic UI is immediately reconciled against the authoritative REST response. On error, the optimistic change is reverted.

### Session Lifecycle Rules

- **Open Trigger(s)**: Cart session created via POST by a reservation participant.
- **Close Trigger(s)**: Cart session closed when the order is submitted to kitchen or waiter explicitly closes the tab.
- **Close Snapshot Contract**: N/A — CartSession is ephemeral; final state is captured when items are transferred to an Order.

### Offline & Reconnection Contract

- **Disconnect UX**: Cart remains visible in its last known state. No writes are blocked (writes go through REST independently).
- **Write Blocking Rule**: Writes are never blocked by WebSocket state. REST continues working regardless of WebSocket connection status.
- **Reconnect Recovery**: On WebSocket reconnect, the client automatically issues a GET request for the full cart state to reconcile any missed changes.

### Key Entities

- **CartSession**: Represents a shared cart bound to a reservation. Contains participants (M2M to User), status (active/closed), and restaurant scope.
- **CartItem**: A line item within a cart session. References a MenuItem, tracks quantity, who added it, and optional comment.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Two authenticated participants in the same session see each other's cart additions within 500ms (measured from REST 201 response to WebSocket event dispatch).
- **SC-002**: Concurrent POST requests for the same menu item from two users result in exactly one CartItem with combined quantity (zero data corruption).
- **SC-003**: After WebSocket disconnection and reconnection, the client's cart state matches the server state (verified by snapshot comparison).
- **SC-004**: Attempting to add an unavailable menu item returns a 400 error; the cart and WebSocket state remain consistent.
- **SC-005**: Closed cart sessions reject all mutation attempts with 409, maintaining data integrity.

## Assumptions

- Guests authenticate via JWT and are linked to a reservation as participants.
- CartSession and CartItem models are the source of truth for active cart state.
- WebSocket connectivity is best-effort; missed messages are recovered via REST re-fetch on reconnect.
- Only one cart session is active per reservation at any time.
- The existing `CartSession` and `CartItem` models with `CartSessionStatus` will be used as the shared cart foundation.
