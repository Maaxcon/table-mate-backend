# Implementation Plan: Offline-First Cart Submit

**Branch**: `orders/18-be-offline-cart-submit`
**Date**: 2026-06-02

## Summary

Replace the abandoned real-time cart (`CartSession`/`CartItem`/`ws/cart/`) with a single atomic POST endpoint that creates orders from an offline-first client cart, with Redis-backed idempotency, server-side pricing, and ws/hall/ broadcast.

## Implementation Steps

### Step 1 — Cleanup
- Remove `CartConsumer` from `apps/orders/consumers.py`
- Remove `ws/cart/` from `apps/orders/routing.py`
- Remove orders routing import from `core/routing.py`
- Remove `cart_group_name` from `common/channels.py`

### Step 2 — Idempotency Module
- Create `common/idempotency.py` with `IdempotencyKeyMixin` (DRF APIView mixin)
- On request: extract `Idempotency-Key` header, check Redis
- On cache hit: return stored 201 response
- On cache miss: process, store key→response in Redis, return

### Step 3 — Order Submit Service
- Create `apps/orders/services.py` with `submit_order()`:
  - `select_for_update()` on Session (find-or-create)
  - `select_for_update()` on MenuItems
  - Validate availability, guest_slot
  - Fetch prices, compute totals/taxes
  - `transaction.atomic()`: create Order + bulk OrderItems + Ticket

### Step 4 — Serializer
- Add `CreateOrderFromCartSerializer` and `CreateOrderItemSerializer` to `apps/orders/serializers.py`
- Accept: `table_id`, `notes`, `items[]`
- Server-side validation: table exists, items available, guest_slot valid

### Step 5 — View & URL
- Add `OrderSubmitView` (APIView with IdempotencyKeyMixin) to `apps/orders/views.py`
- Wire `orders/submit/` in `apps/orders/urls.py`

### Step 6 — Signal
- Create `apps/orders/signals.py` with post_save handler for Order
- On `status == submitted`: broadcast via ws/hall/ group
- Wire signal in `apps/orders/apps.py` ready()

### Step 7 — Tests
- Idempotency: same key twice → one order
- Concurrency: parallel session find-or-create
- Data integrity: pricing from DB, guest_slot validation
- Broadcast: ws/hall/ gets event on submitted
