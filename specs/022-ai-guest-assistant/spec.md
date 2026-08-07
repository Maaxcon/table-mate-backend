# Feature Specification: AI Guest Assistant

**Feature Branch**: `feat/041-AI-guest-assistant`
**Created**: 2026-08-05
**Status**: Draft
**Input**: User description: "little ai guest assistant... able to call different tools in order to be able to answer the customer's questions and perhaps to be able to complete some commands, like booking or adding to the cart. In the future, perhaps i'd like to extend the functionality, better say split it in order to give the admin the more comfortable usage... For that purpose, we could make it agentic with the async on tool calling."

## Clarifications

### Session 2026-08-05

- Q: How is a guest handed off to staff when the assistant cannot help? → A: Async request + staff notification (Option B) — the hand-off is recorded with conversation context, staff are notified via the existing notification stream, and the guest is told staff will follow up.
- Q: How long are assistant conversations and the tool-action audit trail retained? → A: 7 days for conversations, 30 days for the audit trail (Option B, privacy-lean), after which records are deleted.
- Q: How is assistant usage protected from abuse/cost? → A: Per-guest hourly and daily message caps with a friendly limit notice (Option A).
- Q: How long does a pending tool proposal stay valid before it expires? → A: 5 minutes (Option A), after which it cannot be executed and the action is re-proposed.

## User Scenarios & Testing

### User Story 1 - Guest Asks Questions and Gets Accurate Answers (Priority: P1)

A guest opens the in-app chat widget and asks about the menu, ingredients, allergens, opening hours, or reservation policy. The assistant answers using the restaurant's live data — never stale or guessed information.

**Why this priority**: Conversational answers are the core value of the assistant and the foundation every other story builds on; without reliable answers the assistant has no trust.

**Independent Test**: Can be tested by sending a set of prepared questions (menu, allergen, hours, reservation policy) through the chat and verifying the answers match the current restaurant data, including after that data changes.

**Acceptance Scenarios**:

1. **Given** a restaurant with a published menu, **When** a guest asks "what dishes contain gluten", **Then** the assistant lists the matching dishes using current allergen data
2. **Given** a restaurant whose opening hours changed, **When** a guest asks "when are you open tomorrow", **Then** the answer reflects the updated hours
3. **Given** a question the assistant cannot answer reliably, **When** the guest asks it, **Then** the assistant says it cannot answer and offers to connect the guest to staff
4. **Given** a guest asking about prices or dishes, **When** the assistant answers, **Then** the answer only uses data the guest is entitled to see (menu, hours, own reservation/cart) — never other guests' or staff-only data

---

### User Story 2 - Guest Books a Table Through the Assistant (Priority: P1)

A guest requests a table for a party size, date, and time. The assistant checks availability, proposes a booking, asks the guest to confirm, and on confirmation creates the reservation through the same rules a manual booking uses.

**Why this priority**: Booking is one of the two state-changing tools the user explicitly wants; completing a real booking end-to-end proves the tool-calling loop works safely.

**Independent Test**: Can be tested by asking the assistant to book a table for a specific party size/time, confirming the proposal, and verifying a reservation appears in the guest's reservations and respects business hours and capacity.

**Acceptance Scenarios**:

1. **Given** an available slot for the requested party size and time, **When** the guest requests a booking, **Then** the assistant proposes the booking with details and asks for confirmation
2. **Given** a confirmed proposal, **When** the guest confirms, **Then** a reservation is created and the guest sees it in their reservation list
3. **Given** no available slot, **When** the guest requests a booking, **Then** the assistant proposes the nearest alternative times and does not create a reservation until the guest picks and confirms one
4. **Given** a booking request outside business hours, **When** the guest requests it, **Then** the assistant explains the constraint and proposes in-hours alternatives
5. **Given** a booking proposal, **When** the guest rejects or abandons it, **Then** no reservation is created
6. **Given** a proposal created earlier, **When** the guest confirms it after the slot was taken by someone else, **Then** the system re-checks availability at execution time and, if unavailable, does not create the reservation and proposes alternatives

---

### User Story 3 - Guest Adds Items to Their Cart Through the Assistant (Priority: P1)

A guest asks the assistant to add dishes to their cart. The assistant summarizes the item(s) and price, asks the guest to confirm, and on confirmation adds them to the guest's active cart for the current reservation.

**Why this priority**: Adding to cart is the second explicitly requested state-changing tool and proves integration with the shared cart session model.

**Independent Test**: Can be tested by asking the assistant to add a dish with modifiers to the cart, confirming, and verifying the cart contents update correctly for the guest's session.

**Acceptance Scenarios**:

1. **Given** a guest with an active cart session, **When** the guest asks to add a dish, **Then** the assistant proposes the item, price, and any required modifiers and asks for confirmation
2. **Given** a confirmed cart proposal, **When** the guest confirms, **Then** the item is added to the guest's cart and appears with the correct quantity and price
3. **Given** an item that is unavailable or discontinued, **When** the guest asks to add it, **Then** the assistant does not add it and proposes available alternatives
4. **Given** a dish requiring modifiers (size, extras), **When** the guest omits them, **Then** the assistant asks for the missing choices before proposing
5. **Given** a closed cart session, **When** the guest asks to add an item, **Then** the assistant explains the cart is closed and does not add the item

---

### User Story 4 - Guest Modifies or Cancels a Reservation Through the Assistant (Priority: P2)

A guest asks the assistant to change the time/party size of an existing reservation or cancel it. The assistant proposes the change, requires explicit confirmation, and on confirmation performs the change under the same rules as manual changes.

**Why this priority**: Managing the reservation lifecycle through the assistant removes friction once a booking exists and exercises a second set of tool calls.

**Independent Test**: Can be tested by asking the assistant to reschedule and then cancel a reservation, verifying each step requires confirmation and that the final state matches the guest's choice.

**Acceptance Scenarios**:

1. **Given** a guest with an existing reservation, **When** they ask to move it to another time, **Then** the assistant proposes the new time (re-checking availability) and requires confirmation
2. **Given** a guest with an existing reservation, **When** they ask to cancel it, **Then** the assistant shows the cancellation consequence and requires explicit confirmation before cancelling
3. **Given** a cancellation, **When** the guest confirms, **Then** the reservation is cancelled and the freed slot is available to other guests
4. **Given** a modification request that conflicts with business rules, **When** the guest requests it, **Then** the assistant explains the conflict and proposes a valid alternative

---

### User Story 5 - Guest Hands Off to Human Staff (Priority: P2)

When the assistant cannot answer, the guest wants a human, or an action is too sensitive, the guest can request a hand-off. The assistant records a hand-off request with conversation context, notifies staff through the existing notification stream, and tells the guest that staff will follow up.

**Why this priority**: A reliable escape hatch protects the guest experience when automation reaches its limit and avoids frustrated guests.

**Independent Test**: Can be tested by requesting a human in the chat and verifying a hand-off request with the conversation context is recorded and staff receive a notification.

**Acceptance Scenarios**:

1. **Given** an assistant that cannot answer a question, **When** the guest asks for a human, **Then** the assistant records the hand-off request with conversation context and staff are notified
2. **Given** a guest requesting payment handling, **When** the guest asks the assistant, **Then** the assistant does not process payments and refers the guest to staff
3. **Given** a hand-off request, **When** staff is unavailable, **Then** the guest is told their request was recorded and staff will follow up
4. **Given** a guest who requested a hand-off, **When** the guest keeps chatting, **Then** the assistant continues to support the guest until staff follow up

---

### User Story 6 - Assistant Is Extended with New Tools and an Admin Persona (Priority: P3)

The assistant platform supports adding new tools and new assistant personas (for example a future admin assistant for bulk reservation handling, nearest-available-slot lookup, shift, translation, and dish management) without redesign.

**Why this priority**: The user explicitly wants the assistant to grow into a broader staff-facing tool; building the extension mechanism up front keeps future work additive.

**Independent Test**: Can be tested by registering a new tool or a new persona and verifying it is discoverable, executes through the same safety rails (confirmation, authorization, audit), and appears without redeployment of the existing assistants.

**Acceptance Scenarios**:

1. **Given** the assistant platform, **When** a new tool is added, **Then** it is available to assistants without changes to existing assistants
2. **Given** an admin persona, **When** an admin talks to it, **Then** its tool access is bounded by the admin role and every action follows the same confirmation, authorization, and audit rules
3. **Given** a guest persona, **When** it attempts a tool that only the admin persona may use, **Then** the request is denied by the backend regardless of what the assistant says

---

### Edge Cases

- What happens when the guest is not authenticated? The assistant is only reachable by authenticated guests; unauthenticated visitors get a sign-in prompt, not assistant access.
- What happens when the restaurant is closed at the time the guest books? The assistant proposes in-hours alternatives instead of creating the booking.
- What happens when the slot becomes unavailable between proposal and confirmation? Availability is re-checked at execution time; the booking is not created and alternatives are proposed.
- What happens when the guest asks to add an unavailable dish? The item is not added; alternatives are proposed.
- What happens when a required modifier is missing? The assistant asks for the missing choices before proposing the action.
- What happens when the assistant cannot answer a question? It says so and offers a staff hand-off.
- What happens when the guest asks about prices, availability, or their own data? The assistant uses live data only, never guesses or memorized information.
- What happens when the assistant is asked for staff-only or another guest's information? It refuses; the backend also enforces the data boundary at tool execution time.
- What happens when the guest sends an ambiguous request? The assistant asks clarifying questions before proposing any action.
- What happens when a guest exceeds the hourly or daily assistant message cap? The assistant stops accepting messages for the period and shows a friendly limit notice; no model inference is spent on capped messages.
- What happens when the guest confirms a tool proposal after it has expired? The proposal is rejected (5-minute window) and the assistant re-proposes the action against current state.
- What happens when the conversation is interrupted or the guest reconnects later? The conversation history is persisted and can be continued.
- What happens when the same assistant message is delivered twice (network retry)? Duplicate delivery does not create duplicate tool executions (idempotency).
- What happens when the assistant executes a tool but the confirmation message was revoked or the guest changed their mind? Only explicitly confirmed actions execute; a cancelled confirmation produces no state change.
- What happens during a staff hand-off when no staff is online? The request is recorded and staff follow up later.
- What happens if the guest asks the assistant to handle payment? Payment is out of scope for the assistant; it refers the guest to staff.
- What happens when the underlying restaurant data changes mid-conversation (menu update, slot taken)? Tool execution uses the current backend state and re-validates, so answers and actions never rely on stale data.

## Requirements

### Functional Requirements

- **FR-001**: System MUST provide an in-app web chat for authenticated guests through which they can converse with the AI guest assistant
- **FR-002**: The assistant MUST answer questions using the restaurant's current data (menu, allergens, ingredients, prices, opening hours, reservation policy) and MUST NOT invent or guess information
- **FR-003**: The assistant MUST be able to perform tool actions that create, reschedule, or cancel reservations and add items to the guest's cart
- **FR-004**: Every state-changing tool action MUST require explicit guest confirmation of a human-readable summary before it is executed
- **FR-005**: Tool actions MUST be executed through the same backend services and business rules as manual guest actions (business hours, capacity, menu availability, cart session rules) — the assistant MUST NOT bypass constraints
- **FR-006**: Tool execution MUST re-validate availability and context at execution time, not rely on earlier conversation state
- **FR-007**: The assistant MUST be able to propose alternatives (other times, similar dishes) when a requested action is not possible
- **FR-008**: The assistant MUST refuse requests outside the guest's data boundary (other guests' data, staff-only data, financial handling) and the backend MUST enforce the same boundary on every tool execution
- **FR-009**: The assistant MUST NOT handle payments; payment requests MUST be referred to staff
- **FR-010**: All assistant tool actions MUST be recorded in an audit trail (acting guest, channel, tool, inputs, outcome, timestamps) that is retained for review
- **FR-011**: The assistant MUST hand off a conversation by recording a hand-off request with relevant context, notifying staff through the existing staff notification stream, and informing the guest that staff will follow up, when it cannot answer or the guest requests a human
- **FR-012**: Conversation history MUST be persisted so a guest can continue a conversation, and assistant responses MUST be consistent with that history
- **FR-013**: Assistant-delivered messages MUST be delivered as live events to the guest's session and tolerate network retries without duplicate tool execution
- **FR-014**: The assistant platform MUST support registering new tools and new assistant personas (e.g., a future admin assistant) without rearchitecting existing assistants
- **FR-015**: Persona tool access MUST be bounded by the acting user's role and enforced by the backend at execution time
- **FR-016**: Ambiguous guest requests MUST trigger clarifying questions before any action is proposed
- **FR-017**: The assistant model MUST NOT be given credentials, direct network access, or the ability to call the backend itself; its only output MUST be a structured tool-call proposal executed by an app-side execution layer that holds the guest's authenticated session
- **FR-018**: Tool-call proposals MUST conform to strict structured schemas; malformed or out-of-schema proposals MUST be rejected and MUST NOT be executed, and the model MUST be re-prompted
- **FR-019**: Read-only tools MUST be executable silently with results summarized to the guest; state-changing tools MUST always pass the confirmation checkpoint before execution
- **FR-020**: Per turn, the assistant MUST be offered only a small, focused tool set (3-5 tools); when the full tool surface is larger, an intent router MUST narrow the tools to the relevant category before the model selects one
- **FR-021**: The system MUST append relevant current context (selected entity, active reservation, cart, menu state) to the assistant prompt so the model can resolve guest references such as "this table" or "my booking"
- **FR-022**: The system MUST delete conversation history after 7 days and tool-action audit records after 30 days, with cleanup enforced automatically
- **FR-023**: The system MUST enforce per-guest hourly and daily assistant message caps and respond with a friendly limit notice when a cap is reached
- **FR-024**: A pending tool proposal MUST expire 5 minutes after it is issued; expired proposals MUST NOT be executed and the assistant MUST re-propose the action against current state

### Non-Functional Requirements

- **NFR-001**: A guest MUST be able to complete a booking conversation (question, proposal, confirm) within 2 minutes
- **NFR-002**: Assistant replies MUST be delivered to the guest within 5 seconds under normal load
- **NFR-003**: The assistant MUST support at least 2 concurrent conversations per active guest session without degradation
- **NFR-004**: Prepared evaluation questions (menu, allergens, hours) MUST be answered correctly in at least 95% of cases without staff escalation
- **NFR-005**: No state-changing action MAY be executed without the explicit confirmation captured in FR-004; this MUST be verifiable from the audit trail
- **NFR-006**: The platform MUST be built so future assistants (e.g., admin) can reuse the tool infrastructure without duplicating safety rails
- **NFR-007**: At least 95% of tool-call proposals MUST validate against their strict schema on the first attempt with the configured model

### Assistant Execution Architecture

The assistant follows the "model proposes, the application disposes" pattern. The model is a pure reasoning layer: it receives the guest's message, the allowed tools, and current context, and produces a single structured action proposal. It never holds credentials and never makes requests directly.

- **Proposal Only**: The model MUST NOT be given credentials, direct network access, or the ability to call the backend itself. Its only output is a structured tool-call proposal.
- **Execution by the App**: An app-side execution layer (the client holding the guest's session, or a lightweight backend middleware) catches the proposal, validates it against the strict schema, applies the human-in-the-loop confirmation checkpoint for state-changing actions, and executes it through the same authenticated service paths the normal UI buttons use.
- **Small, Focused Tool Catalog**: Per turn, the model is offered only 3-5 specific tools. When the full tool surface is larger, an intent router first categorizes the request, then a narrowed tool set is offered for that category.
- **Strict Structured Output**: Proposals MUST conform to strict schemas; out-of-schema output is rejected without execution and the model is re-prompted.
- **UI Context Injection**: Current context is appended to the prompt so the model can resolve guest references like "this table" or "my booking" against concrete entities.
- **Read vs. Write Separation**: Read-only tools execute silently and are summarized; state-changing tools always pass the confirmation checkpoint.

### Canonical Contract Impact

- **Impacted Entities**: Reservation (used by tools), CartSession, CartItem, Restaurant, Menu, MenuItem, RestaurantSettings (read for answers), new Conversation/Message/ToolCall records
- **Contract Delta**:
  - New conversation entities (see Key Entities) that reference the guest and restaurant and store the assistant conversation, tool proposals, and execution outcomes
  - No shape changes to Reservation, CartSession, or CartItem — tool calls reuse existing creation/mutation paths
  - New live events for assistant messages, action proposals, and action results (see Realtime Event Contracts)
- **Backend Source of Truth Rule**: All state-changing tool actions are executed by the existing backend services as if performed by the guest directly; the assistant is a conversational front end to the same authoritative backend

### Role Access Matrix

- **Customer**: Start assistant conversations, ask questions, and perform tool actions limited to their own reservations and their own active cart
- **Customer Restricted**: Cannot see or act on other guests' data, staff-only data, financials, or reservations that are not their own; cannot bypass confirmation or business rules
- **Cook**: Unaffected by the guest assistant; no access to guest conversations
- **Cook Restricted**: Cannot act through the assistant or view guest conversation history
- **Waiter**: Unaffected by the guest assistant for day-to-day work; receives staff hand-off requests for their restaurant
- **Waiter Restricted**: Cannot act on behalf of guests through the assistant; cannot view guest conversations except the context attached to a hand-off
- **Admin**: May configure assistant behavior for their restaurant and may review assistant conversation/action audit logs
- **Admin Restricted**: Guest-facing assistant tool access is role-bounded; an admin persona (future work) MUST NOT inherit guest-tool privileges and vice versa

### Realtime Event Contracts

- **Event**: `ASSISTANT_MESSAGE`
- **Audience**: the authenticated guest who is conversing (session-scoped)
- **Transport**: websocket channel for the guest session
- **Payload**: message_id, role, text, created_at, schema_version
- **schema_version**: 1; additive-only forward compatibility
- **Unknown Version Handling**: clients ignore messages with an unsupported schema_version rather than crashing

- **Event**: `ASSISTANT_ACTION_PROPOSED`
- **Audience**: the authenticated guest (session-scoped)
- **Transport**: websocket channel for the guest session
- **Payload**: proposal_id, tool, summary, expires_at, schema_version
- **schema_version**: 1
- **Unknown Version Handling**: clients ignore unsupported versions

- **Event**: `ASSISTANT_ACTION_RESULT`
- **Audience**: the authenticated guest (session-scoped)
- **Transport**: websocket channel for the guest session
- **Payload**: proposal_id, tool, outcome, reference_id (e.g., reservation/cart id), schema_version
- **schema_version**: 1
- **Unknown Version Handling**: clients ignore unsupported versions

### Event Delivery Guarantees

- **Delivery Guarantee**: At-least-once delivery for assistant events, matching the constitution baseline
- **Replay Window**: On reconnect, the guest session MUST receive any missed assistant events from the disconnection window so the conversation stays consistent
- **Idempotency Strategy**: Tool execution MUST be idempotent — a duplicated delivery of the same confirmed proposal MUST NOT create a duplicate reservation or duplicate cart items (execution keyed on proposal_id)

### Transaction & State Authority

- **Authoritative Transition**: Reservation create/reschedule/cancel and cart-item additions are performed by the existing backend services; the assistant never mutates state directly
- **Atomic Group**: A confirmed tool action's state change (e.g., reservation row, cart line, notification/event) commits atomically through the same transaction rules as the manual path
- **Rollback Rule**: If the state change fails validation (slot taken, cart closed), no partial change persists and the guest receives an error with alternatives
- **No-Optimistic-Truth Rule**: The assistant must not present a confirmation success before the backend transaction has committed; the live event only fires after commit

### Session Lifecycle Rules

- **Open Trigger(s)**: A tool-created reservation follows the same reservation lifecycle (pending/active/cancelled) as a manually created one
- **Close Trigger(s)**: Reservation cancellation through the assistant follows the manual cancellation rules, including freeing the slot for other guests
- **Close Snapshot Contract**: Reservation/occupancy analytics remain sourced from the reservation and session records; assistant activity does not introduce a parallel occupancy model

### Frontend Surface Contract

- **Role Tree Mounting Rule**: The assistant chat widget mounts only for the customer role tree; staff roles do not mount the guest chat surface
- **Execution Layer Rule**: The surface that renders the chat is the execution layer for assistant tool calls — it holds the guest's session token, never passes it to the model, and issues the same authenticated requests the normal UI would; the model never receives credentials or performs requests itself
- **Floor Plan State Source**: N/A — the guest assistant does not render floor-plan state
- **Spatial Editor Separation**: N/A — no spatial editing surface in this feature

### Offline & Reconnection Contract

- **Disconnect UX**: While disconnected, the chat shows a persistent error state and blocks sending messages and confirming actions
- **Write Blocking Rule**: Message sending and tool confirmation are disabled while disconnected
- **Reconnect Recovery**: After reconnect, the client refreshes the conversation state (replayed assistant events) before enabling writes again

### Destructive Action Confirmation Contract

- **Impacted Actions**: Reservation cancellation (and any other state-changing tool action)
- **Checkpoint Rule**: Any state-changing tool proposal MUST surface a confirmation dialogue ("The assistant wants to <action>. Approve?") with a human-readable summary and consequence before execution; the guest's approval or dismissal is the only path to or away from execution
- **Read-Only Rule**: Read-only tools MUST NOT require confirmation and MUST only be summarized to the guest
- **Required Fields**: A human-readable summary of the action and its consequence MUST be shown before confirmation; cancellation MUST state the reservation that will be cancelled
- **Dismiss/Cancel Behavior**: Dismissing a proposal (outside tap or explicit cancel) MUST NOT execute the action and MUST notify the assistant so it can follow up

### Key Entities

- **Conversation**: A persisted assistant conversation bound to a guest and restaurant, with a status and timestamps; enables history and continued conversations
- **Message**: A message within a Conversation (guest or assistant), with ordering, text, and a reference to any tool proposal/result it produced
- **Tool Proposal**: A proposed state-changing action awaiting guest confirmation, carrying the tool name, inputs, human-readable summary, and a 5-minute expiry; the unit of idempotency
- **Tool Call / Action Record**: The executed action audit entry — acting guest, tool, inputs, outcome, reservation/cart reference, timestamps
- **Reservation** (existing): Created, rescheduled, or cancelled through assistant tools using the existing reservation rules
- **CartSession / CartItem** (existing): Items added to the guest's active cart through assistant tools using the existing cart rules
- **Staff Hand-off Request**: A recorded request to connect a guest to staff, carrying conversation context; staff are notified via the existing notification stream and follow up asynchronously

## Success Criteria

### Measurable Outcomes

- **SC-001**: A guest can complete a full table booking through the assistant (request, proposal, confirm, visible in reservations) without leaving the chat
- **SC-002**: A guest can add a dish with required modifiers to their cart through the assistant and see it reflected in the cart with correct quantity and price
- **SC-003**: At least 95% of prepared evaluation questions about menu, allergens, opening hours, and reservation policy are answered correctly without staff escalation
- **SC-004**: No state-changing action is executed without explicit guest confirmation, verifiable from the audit trail
- **SC-005**: Zero assistant tool actions can access another guest's or staff-only data across tested boundary scenarios
- **SC-006**: Duplicate message delivery never produces a duplicate reservation or duplicate cart line
- **SC-007**: A new tool or a new assistant persona (e.g., admin) can be added without changes to existing assistants, verified by a live demo of one added tool and one added persona
- **SC-008**: A guest can hand off to staff with context in under 1 minute from their request
- **SC-009**: No tool call is ever executed with credentials held by the model or through a direct model request; all executions route through the user-authenticated execution path (verifiable via tests and the audit trail)
- **SC-010**: Malformed or out-of-schema tool proposals are rejected without execution (zero executed across tested cases)
- **SC-011**: Conversation history is deleted after 7 days and tool-action audit records after 30 days, verifiable by inspecting records past their retention age
- **SC-012**: A guest exceeding the hourly or daily message cap is blocked from further assistant messages for the period and sees a friendly notice (no model inference is spent on capped messages)
- **SC-013**: A tool proposal older than 5 minutes cannot be executed; the assistant re-proposes the action against current state

## Assumptions

- The assistant is delivered through an in-app web chat widget in the customer application (user-confirmed); messaging-platform channels are out of scope for this feature but the core must be transport-decoupled for later addition
- Every state-changing tool action requires explicit guest confirmation (user-confirmed); the assistant never auto-executes bookings, cart changes, or cancellations
- The existing authentication (JWT) and role model are reused; the assistant acts with the guest's identity and permissions
- The existing reservation, cart, and menu systems are reused as the authoritative execution paths; no parallel booking or inventory model is introduced
- Payment handling is out of scope for the assistant
- The future admin assistant (bulk reservations, nearest-slot lookup, shift/translation/dish management) is OUT of scope for this feature; only the extension mechanism (new tools + personas) is in scope so it can be added later
- Conversation history is retained for 7 days and the tool-action audit trail for 30 days, after which records are deleted automatically (user-confirmed); no indefinite retention
- The assistant answers in the guest's conversation language, using the restaurant's supported languages as the bound
- A guest may use the assistant before and during their visit (pre-booking and while a reservation/session is active)
- The AI model runs on Ollama with structured output/JSON mode (per project decision); because it is a small local model, the tool catalog is kept intentionally small with intent routing and strict schemas (FR-018, FR-020)
- The model NEVER holds credentials or makes direct requests; execution always goes through an app-side execution layer under the guest's authenticated session (FR-017)
- The execution layer is the customer client (which holds the session token) and/or a lightweight backend middleware; the exact split is decided in the plan
- The assistant chat widget, proposal confirmation dialogue, and offline/reconnect handling are implemented in the customer web app repo per the Frontend Surface, Offline & Reconnection, and Destructive Action Confirmation contracts in this spec (constitution C-I — one shared spec for frontend and backend)
