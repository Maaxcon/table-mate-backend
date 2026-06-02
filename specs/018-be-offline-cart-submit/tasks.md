# Tasks: Offline-First Cart Submit

## Cleanup Phase

- [ ] T001 Remove CartConsumer, ws/cart/ routing, cart_group_name helper

## Core Implementation

- [ ] T002 Create common/idempotency.py with Redis-backed IdempotencyKeyMixin
- [ ] T003 Create apps/orders/services.py with submit_order()
- [ ] T004 Add CreateOrderFromCartSerializer to apps/orders/serializers.py
- [ ] T005 Add OrderSubmitView with IdempotencyKeyMixin to apps/orders/views.py
- [ ] T006 Wire POST /api/orders/submit/ in apps/orders/urls.py
- [ ] T007 Create apps/orders/signals.py with ws/hall/ broadcast on submitted
- [ ] T008 Wire signal in apps/orders/apps.py ready()

## Tests

- [ ] T009 Write idempotency test (same key twice = one order)
- [ ] T010 Write data integrity test (pricing from DB, guest_slot validation)
- [ ] T011 Write concurrency test (parallel session find-or-create)
