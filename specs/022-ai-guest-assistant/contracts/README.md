# Assistant Contracts

This directory defines the external contracts for the AI guest assistant. They are the source of truth that both the backend (`apps/assistant`) and the customer web app implement.

| Document | Contents |
|----------|----------|
| `assistant-api.md` | REST endpoints, status codes, auth, rate limiting |
| `events.md` | WebSocket event contracts (`ASSISTANT_MESSAGE`, `ASSISTANT_ACTION_PROPOSED`, `ASSISTANT_ACTION_RESULT`) |
| `tools.md` | Tool catalog, intent router, per-tool JSON schemas, execution semantics, extension mechanism |

## Transport Rules (Constitution C4)

- **REST = create/mutate only.** Sending messages, confirming/rejecting proposals, and requesting hand-offs are REST mutations. No live state is read over REST beyond bounded history snapshots.
- **WebSocket = live read + event delivery only.** Assistant replies, proposals, and results are delivered as typed, versioned WS events to the guest's conversation group.
- **Auth**: all endpoints require `IsAuthenticated` (JWT). Identity = user pk or `guest_id`/cart-session claim; ownership is enforced on every conversation/proposal access (FR-008, C3).
- **The model never touches any of this.** It receives no credentials and no URL; its only output is a structured tool-call proposal that the backend validates and executes (FR-017, SC-009).
- **Execution layer**: the backend assistant API is the execution layer; the frontend only issues authenticated requests and renders confirmation dialogues (see `research.md` R1).
