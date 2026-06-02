# Feature Specification: Offline-First Cart Submit with Idempotency

**Feature Branch**: `orders/18-be-offline-cart-submit`
**Created**: 2026-06-02
**Status**: Finalized
**Input**: Team architecture alignment — drop real-time shared server cart, adopt offline-first client cart with single POST submit.

## User Stories

### Customer — Submit Order from Local Cart
As a customer, I can tap "Send Order" after filling my cart in localStorage, and the backend atomically creates the order, resolves the table session, generates kitchen tickets, and notifies staff via hall channel — without duplicate submissions from network retries.

**Acceptance**:
1. **Given** a valid JWT, **When** POST /api/orders/submit/ with `table_id`, `items[]`, and `Idempotency-Key` header, **Then** backend creates Order + OrderItems + Ticket, returns 201 with order details.
2. **Given** the same `Idempotency-Key` sent twice, **Then** second request returns the same 201 response without creating a duplicate order.
3. **Given** an invalid/expired `Idempotency-Key` format, **Then** backend returns 400.
4. **Given** an unavailable menu item, **Then** backend returns 409.
5. **Given** a closed table session already exists, **Then** backend reuses the open session rather than creating a new one.

## Requirements

1. **FR-001**: Single POST `/api/orders/submit/` accepts `table_id`, `notes`, `items[]` (menu_item_id, quantity, guest_slot, comment).
2. **FR-002**: Frontend price data in payload is ignored — prices fetched from DB.
3. **FR-003**: Idempotency-Key header (UUID) checked against Redis; duplicate keys replay cached 201 response.
4. **FR-004**: Session resolved via `select_for_update()` — find existing OPEN session for table or create one.
5. **FR-005**: Guest slot validated against session guest_count.
6. **FR-006**: Tax calculated server-side via `decimal_places=4` quantize from `RestaurantSettings.default_tax_rate`.
7. **FR-007**: Ticket created per order, linked to OrderItems.
8. **FR-008**: `ws/hall/` broadcast fires only on Order status transition to `submitted`.
9. **FR-009**: Old `CartConsumer` and `ws/cart/` routing removed.

## Key Entities

- `Order`, `OrderItem`, `Session`, `Ticket` — existing models reused.
- `MenuItem.price` — source of truth for unit pricing.
- `RestaurantSettings.default_tax_rate` — source for tax computation.
- Redis cache — idempotency key store.
