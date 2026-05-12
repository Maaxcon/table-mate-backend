# Implementation Plan: Tablemate Backend MVP API

**Branch**: `001-tablemate-backend-mvp` | **Date**: 2026-05-07 | **Spec**: [Tablemate Backend MVP Spec](spec.md)
**Input**: Feature specification from `/specs/001-tablemate-backend-mvp/spec.md`

## Summary

Implement backend MVP for Tablemate using Django 5 + DRF + JWT + Google OAuth, with Redis/Channels realtime transport and strict domain architecture (Skinny Views, Fat Services, Selectors). The plan aligns backend APIs and websocket contracts with frontend module expectations.

## Technical Context

**Language/Version**: Python 3.12, Django 5+  
**Primary Dependencies**: DRF, `djangorestframework-simplejwt`, Redis, Django Channels  
**Storage**: PostgreSQL (transactional reservation safety)  
**Testing**: Django test suite (`pytest` or Django test runner), contract + integration tests  
**Target Platform**: Linux containers via Docker/Docker Compose  
**Project Type**: Backend web service (REST + WebSocket)  
**Performance Goals**: Deterministic reservation conflict handling, low-latency cart/hall event delivery  
**Constraints**: Service-layer business logic only, selector-layer complex queries, role-based permissions, no AI and no multi-restaurant tenancy  
**Scale/Scope**: MVP domains `users/authentication/restaurants/editor/reservations/orders/menu/payments` plus webhook-confirmed payment transition path

## Constitution Check

*GATE: Must pass before implementation begins and re-check before PR.*

| Gate | Rule | Status | Action |
|------|------|--------|--------|
| C1 | Skinny Views, Fat Services, Selectors | PASS-WITH-GUARD | Enforce via task review and code ownership in app services/selectors |
| C2 | Django 5 + DRF + PostgreSQL + Redis/Channels | PASS-WITH-GAPS | Add missing dependencies/settings in setup phase |
| C3 | UUID/Timestamp mixins on domain models | PASS-WITH-GAPS | Implement `common/mixins.py` and migrate models |
| C4 | Typed service/selector boundaries + domain exceptions | PASS-WITH-GAPS | Implement `common/exceptions.py`, typed service signatures |
| C5 | CI quality/security gates | PARTIAL | Ensure workflow includes lint + bandit + safety + tests |
| C6 | JWT + Google OAuth + role permissions | PARTIAL | Implement auth service, permissions, and endpoint coverage |

## Project Structure

### Documentation (this feature)

```text
specs/001-tablemate-backend-mvp/
├── spec.md
├── plan.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
core/
├── settings/
│   ├── base.py
│   ├── local.py
│   └── production.py
├── asgi.py
├── wsgi.py
└── urls.py

apps/
├── users/
├── authentication/
├── restaurants/
├── editor/
├── reservations/
├── orders/
│   ├── models/
│   │   ├── cart_session.py
│   │   └── cart_item.py
│   └── api/
│       └── v1/
├── payments/
│   └── api/
│       └── v1/
└── menu/

common/
requirements/
.github/workflows/
```

**Structure Decision**: Single backend service with domain-sliced Django apps and explicit service/selector boundaries.

## Phase Plan

### Phase 1 - Setup

1. Split settings into `core/settings/{base,local,production}.py`.
2. Set `AUTH_USER_MODEL` in `core/settings/base.py` to the actual custom user model path (`<app_label>.User`, for example `authentication.User`) before the first `manage.py migrate`.
3. Add bootstrap custom `User` model early in that app so auth model resolution is valid for initial migrations.
4. Normalize environment variables in `.env.example`.
5. Add/verify dependencies for JWT, OAuth verification, Redis/Channels.
6. Create missing app/package skeletons (`users`, `payments`, `orders/models/*`, `orders/api/v1/*`).
7. Create baseline `services.py` and `selectors.py` files per app.

### Phase 2 - Foundational

1. Implement `UUIDMixin` and `TimestampMixin`.
2. Implement domain exceptions and permission classes.
3. Establish enum convention: `models.TextChoices` for role and all status fields (`table`, `order`, `order_item`, `ticket`, `session`).
4. Add schema/type contract pipeline: generate validated OpenAPI (`spectacular --validate --file schema.yaml`) and enforce CI drift checks with frontend type generation.
5. Seed foundational `VoidReason` codes (`mispick`, `guest_changed_mind`, `quality_issue`, `out_of_stock`).
6. Add foundational `RestaurantSettings` fields (`timezone`, `currency`, `locale`, `working_hours`, `default_tax_rate`, `default_service_charge`) and wire reservation/payment dependencies.
7. Add foundational financial columns (tax/discount/tip defaults) on `Order` and `OrderItem`.
8. Make `on_delete` policies explicit with protection baseline (`OrderItem.menu_item`, all `*.restaurant` FKs -> `PROTECT`).
9. Configure DRF JWT auth defaults.
10. Configure Channels + Redis routing.
11. Align core URL and websocket routing.
12. Enforce CI quality/security pipeline.

### Phase 3 - US1 Auth

1. Implement custom user model (`AbstractBaseUser + PermissionsMixin`, `USERNAME_FIELD = email`) and selectors.
2. Implement Google auth service and JWT flow.
3. Implement auth serializers/views/urls.
4. Add auth contract and integration tests.

### Phase 4 - US2 Reservation Safety

1. Implement editor table and reservation models.
2. Implement availability selectors.
3. Implement transaction-safe reservation service with 409 conflict mapping.
4. Implement reservations/editor APIs.
5. Add reservation contract + race-condition tests.

### Phase 5 - US3 Public Menu + Permission Matrix

1. Implement category/menu item models and selectors.
2. Implement public menu read APIs (`AllowAny`).
3. Apply role permissions across protected modules.
4. Add menu contract + permission matrix tests.

### Phase 6 - US4 Orders Cart Realtime

1. Implement cart session/item models.
2. Implement cart selectors/services with participant checks.
3. Implement versioned orders API under `apps/orders/api/v1`.
4. Implement cart websocket consumer/routing/events.
5. Add cart REST + websocket integration tests.

### Phase 7 - US5 Staff/Admin Operations

1. Implement restaurant model/service/selector/API.
2. Implement editor position update service.
3. Implement hall websocket consumer/events.
4. Implement reservation status update policy for staff roles.
5. Add staff ops + hall event tests.

### Phase 8 - US6 Payment Webhook Authority

1. Implement payment webhook endpoint in `apps/payments` with signature validation.
2. Implement idempotency using provider event identifiers in payments service layer.
3. Implement dedicated persistence models: `Payment` (unique `provider_transaction_id`) and `WebhookEvent` (unique provider `event_id`).
4. Implement atomic `unpaid -> paid` transition with kitchen ticket injection.
5. Emit `PAYMENT_CONFIRMED` and `KITCHEN_TICKET_INJECTED` events from payments service layer.
6. Add webhook contract + idempotency integration tests.

### Phase 9 - Polish

1. Add seed scripts for local/demo data.
2. Update docs (`README.md`, `CONTRIBUTING.md`).
3. Run full QA: lint, bandit, safety, tests.
4. Final contract sanity with frontend docs.

## Dependencies & Execution Order

- Phase 1 and 2 are strict blockers.
- US1, US2, US3 start after foundational phase.
- US4 depends on reservation + menu domain maturity.
- US5 can run in parallel with late US4 once permission layer is stable.
- US6 depends on orders/ticket lifecycle readiness from US4 and role/event foundation from US2.
- Polish runs last.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None currently | N/A | N/A |
