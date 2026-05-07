# Implementation Plan: Tablemate Backend MVP API

**Branch**: `001-tablemate-backend-mvp` | **Date**: 2026-05-07 | **Spec**: [Tablemate Backend MVP Spec](/Users/kurilchukmaks/Desktop/table-mate/table-mate-backend/specs/001-tablemate-backend-mvp/spec.md)
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
**Constraints**: Service-layer business logic only, selector-layer complex queries, role-based permissions, no AI/payments/multi-restaurant  
**Scale/Scope**: MVP domains `users/authentication/restaurants/editor/reservations/orders/menu`

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
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
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
└── menu/

common/
requirements/
.github/workflows/
```

**Structure Decision**: Single backend service with domain-sliced Django apps and explicit service/selector boundaries.

## Phase Plan

### Phase 1 - Setup

1. Split settings into `core/settings/{base,local,production}.py`.
2. Normalize environment variables in `.env.example`.
3. Add/verify dependencies for JWT, OAuth verification, Redis/Channels.
4. Create missing app/package skeletons (`users`, `orders/models/*`, `orders/api/v1/*`).
5. Create baseline `services.py` and `selectors.py` files per app.

### Phase 2 - Foundational

1. Implement `UUIDMixin` and `TimestampMixin`.
2. Implement domain exceptions and permission classes.
3. Configure DRF JWT auth defaults.
4. Configure Channels + Redis routing.
5. Align core URL and websocket routing.
6. Enforce CI quality/security pipeline.

### Phase 3 - US1 Auth

1. Implement custom user model and selectors.
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

### Phase 8 - Polish

1. Add seed scripts for local/demo data.
2. Update docs (`README.md`, `CONTRIBUTING.md`).
3. Run full QA: lint, bandit, safety, tests.
4. Final contract sanity with frontend docs.

## Dependencies & Execution Order

- Phase 1 and 2 are strict blockers.
- US1, US2, US3 start after foundational phase.
- US4 depends on reservation + menu domain maturity.
- US5 can run in parallel with late US4 once permission layer is stable.
- Polish runs last.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None currently | N/A | N/A |
