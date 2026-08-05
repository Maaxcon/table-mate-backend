# Assistant Tool Catalog & Schemas

## Intent router

Deterministic router (`services/router.py`) categorizes each user message before the model turn. Output: one of `info`, `booking`, `cart`, `none`. It narrows the tool set offered to the model to ≤ 5 per turn (FR-020).

| Intent | Offered tools | Nature |
|--------|---------------|--------|
| `info` | `get_menu`, `get_restaurant_info`, `check_availability` | read-only |
| `booking` | `check_availability`, `create_reservation`, `reschedule_reservation`, `cancel_reservation` | read + write |
| `cart` | `get_menu`, `add_to_cart` | read + write |
| `none` | — | plain reply / clarifying question / hand-off offer |

**Execution semantics (FR-019)**

- Read-only tools (`get_menu`, `get_restaurant_info`, `check_availability`): executed silently by the backend during the model turn; results are injected back into the prompt and summarized to the guest as an `ASSISTANT_MESSAGE`. No confirmation, no proposal event.
- Write tools (`create_reservation`, `reschedule_reservation`, `cancel_reservation`, `add_to_cart`): never auto-execute. The model emits a proposal; the backend validates, stores a `ToolProposal` (5-min expiry), and emits `ASSISTANT_ACTION_PROPOSED`. Execution happens only via `POST proposals/{id}/confirm/` (FR-004, Checkpoint Rule).

## Proposal schema (model output envelope)

The model always outputs one JSON object with a single top-level discriminant:

```json
{ "kind": "reply", "text": "string" }
```

or

```json
{
  "kind": "tool_call",
  "tool": "<registered tool name>",
  "arguments": { "...": "validated per-tool params" }
}
```

Any other shape is malformed → rejected, re-prompted once, then fallback message (FR-018). Tool names and arguments are validated against the per-tool schema below **and** the caller's persona/role (FR-015).

## Per-tool schemas

Field notes: `date` is `YYYY-MM-DD`, `time` is `HH:MM` (24 h, restaurant-local), ids are the entity `public_id` UUIDs. Optional fields marked `?`.

### `get_menu` (read-only)

```json
{ "query?": "string", "category_id?": "uuid", "available_only?": true, "language?": "string" }
```

- Searches `MenuItem` (title/description in conversation language via translation tables with default-locale fallback), returns name, price (`Decimal(14,4)` formatted), availability, allergens, ingredients.
- Data boundary: only public menu data (FR-008).

### `get_restaurant_info` (read-only)

```json
{ "topic?": "hours|address|policy|payment|contact" }
```

- Opening hours, address, reservation policy, supported languages, currency. `payment` → explains payment is handled by staff (FR-009), no financial data.

### `check_availability` (read-only)

```json
{ "date": "YYYY-MM-DD", "time": "HH:MM", "party_size": "int" }
```

- Runs the existing availability/overlap selectors; returns available slots (and nearest alternatives when the exact slot is taken / outside business hours, FR-007).

### `create_reservation` (write → confirm)

```json
{ "date": "YYYY-MM-DD", "time": "HH:MM", "party_size": "int", "notes?": "string", "table_id?": "uuid" }
```

- On confirm: re-checks availability/business hours (FR-006) then creates via the existing reservation service (FR-005). Reference id = reservation `public_id`.
- Errors at execution: `slot_taken`, `outside_business_hours`, `capacity_exceeded`.

### `reschedule_reservation` (write → confirm)

```json
{ "reservation_id": "uuid", "date?": "YYYY-MM-DD", "time?": "HH:MM", "party_size?": "int" }
```

- Applies to the guest's own reservation only. On confirm: re-checks availability then updates via the existing service. Reference id = reservation `public_id`.
- Errors: `reservation_not_found`, `not_owner`, `slot_taken`, `outside_business_hours`.

### `cancel_reservation` (write → confirm)

```json
{ "reservation_id": "uuid", "reason?": "string" }
```

- Cancellation is a Destructive Action: the confirmation dialogue MUST state the exact reservation being cancelled (Checkpoint Rule). On confirm: cancels via the existing service (slot freed). Reference id = reservation `public_id`.
- Errors: `reservation_not_found`, `not_owner`, `already_cancelled`.

### `add_to_cart` (write → confirm)

```json
{
  "menu_item_id": "uuid",
  "quantity": 1,
  "modifiers": [{ "modifier_id": "uuid", "option_id?": "uuid", "value?": "string" }],
  "guest_comment?": "string"
}
```

- Applies to the guest's active `CartSession` for their current reservation. On confirm: re-checks `is_available` + active cart (FR-006) then adds via the existing cart service. Reference id = cart session `public_id`.
- Required modifiers missing at proposal time → the assistant asks for them before proposing (US-3/AS-4).
- Errors: `cart_closed`, `item_unavailable`, `modifier_required`.

## Error codes (execution audit)

`slot_taken`, `outside_business_hours`, `capacity_exceeded`, `reservation_not_found`, `not_owner`, `already_cancelled`, `cart_closed`, `item_unavailable`, `modifier_required`, `proposal_expired`, `proposal_already_processed`, `schema_rejected`.

## Extension mechanism (FR-014 / FR-015 / US-6)

- `services/registry.py` holds a `ToolRegistry`: `name → {schema, executor, needs_confirmation}`. A new tool = register entry + executor reusing existing services; existing assistants are untouched (US-6/AS-1).
- Personas (`guest`, future `admin`) bind a set of allowed tools. Tool access is bound to the acting role at dispatch and denied server-side regardless of model output (FR-015, US-6/AS-2/AS-3).
- The intent router's category→tool mapping is data-driven from the registry so a new category/tool needs no assistant rewrite.
