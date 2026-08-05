# Implementation Plan: Staff Shift Scheduler

**Branch**: `feat/shift-scheduler` | **Date**: 2026-07-27 | **Spec**: `specs/020-shift-scheduler/spec.md`
**Input**: Feature specification for staff shift scheduling — CRUD shifts, date-range filtering, monthly hour summaries, and bulk copy across dates.

## Summary

Implement a complete staff shift scheduling system within the existing `apps/shifts/` app. Admin users can create, read, update, delete, and copy shifts across dates. Staff users (waiter, cook) can view their own schedule. All operations are restaurant-scoped via JWT auth. The feature is already built; this plan documents the architecture and remaining validation.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: Django 5+, DRF, djangorestframework-simplejwt
**Storage**: PostgreSQL (Shift table with restaurant FK, employee FK, date, start_time, end_time, notes)
**Testing**: pytest via Django test runner
**Target Platform**: Linux server (Docker)
**Project Type**: Web service (Django REST API)
**Performance Goals**: Month summary for 500 shifts under 500ms; copy 20 shifts to 5 dates under 2s
**Constraints**: Restaurant-scoped via JWT; staff read-only; admin full CRUD
**Scale/Scope**: Single restaurant schedule management; no cross-restaurant operations

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Rule | Status | Evidence in Plan |
|------|------|--------|------------------|
| C1 | Right role, right moment, zero ambiguity is preserved | PASS | Shift data is REST-only (no live state); roles get correct access via `get_permissions()` in ShiftViewSet |
| C2 | Canonical shared entity contracts are preserved | PASS | Shift entity defined in constitution v2.1.0; no changes to existing entities |
| C3 | Role access matrix is backend-enforced and structurally reflected in clients | PASS | Admin: full CRUD; Staff (waiter/cook): read-only via `IsAdmin`/`IsStaff` permissions; Customer: no access |
| C4 | Live state uses WebSocket-only typed/versioned events; REST is create/mutate only | PASS | Shift operations are REST-only (no WebSocket events for shift changes) |
| C5 | Delivery guarantee supports at-least-once semantics and reconnect replay | N/A | No WebSocket events emitted for shift operations |
| C6 | Payment confirmation is webhook-only with signature validation | N/A | No payment involvement |
| C7 | Void flow is atomic with explicit rollback and audit data | N/A | No void operations |
| C8 | Session lifecycle is explicit | N/A | No session impact |
| C9 | Kitchen queue ordering preserves injection-time priority | N/A | No kitchen impact |
| C10 | Auth uses role-scoped tokens with immediate invalidation on role change | PASS | ShiftViewSet uses `IsAdmin`/`IsStaff` from existing JWT infrastructure; restaurant_id from token |
| C11 | Floor layout updates are immutable/versioned | N/A | No layout impact |
| C12 | Financial records are externally read-only; AVG PREP is query-time | N/A | No financial impact |
| C13 | Frontend-only constraints | N/A | Backend-only feature scope |
| C14 | Mandatory backend stack and architecture are respected | PASS | Uses Django/DRF, skinny views, fat services (`create_shift`/`update_shift`/`copy_shifts`), selectors (`list_shifts`/`get_month_summary`), RestaurantScopedViewSetMixin |

## Project Structure

### Documentation (this feature)

```text
specs/020-shift-scheduler/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 — decisions (if generated)
├── data-model.md        # Phase 1 — entity definitions
├── quickstart.md        # Phase 1 — validation scenarios
├── contracts/           # Phase 1 — interface contracts
├── checklists/
│   └── requirements.md  # Requirements validation checklist
└── tasks.md             # Phase 2 — actionable tasks (via speckit-tasks)
```

### Source Code (repository root)

```text
apps/shifts/
├── __init__.py
├── admin.py
├── apps.py
├── models.py            # Shift model
├── serializers.py       # ShiftSerializer, ShiftWriteSerializer, CopyShiftsSerializer
├── services.py          # create_shift, update_shift, delete_shift, copy_shifts
├── selectors.py         # list_shifts, get_month_summary, get_employee_month_hours
├── urls.py              # Router registration
├── views.py             # ShiftViewSet
└── migrations/
    └── *.py             # DB migrations
```

**Structure Decision**: Existing `apps/shifts/` app follows the established Django app pattern with skinny views, fat services, and selectors. No structural changes needed.

## Complexity Tracking

No constitution violations — all gates pass. Complexity tracking section is not applicable.
