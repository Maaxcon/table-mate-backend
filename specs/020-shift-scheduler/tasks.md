# Tasks: Staff Shift Scheduler

**Input**: Design documents from `specs/020-shift-scheduler/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Test tasks are included where the spec or constitution mandates verification. Role-based access and transactional integrity are in scope.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 [P] Verify `apps/shifts/` app is registered in Django `INSTALLED_APPS` and migrations applied
- [ ] T002 [P] Verify `apps/shifts/urls.py` is included in project root URL configuration

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be verified

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T003 [P] Verify `RestaurantScopedViewSetMixin` in `common/api/__init__.py` provides `get_restaurant_id()` via `get_restaurant_id_from_auth()`
- [ ] T004 [P] Verify `ShiftViewSet` in `apps/shifts/views.py` uses `get_restaurant_id_from_auth()` (not `self.get_restaurant_id()`) in `list`, `perform_create`, `copy`, and `month_summary`
- [ ] T005 [P] Verify Shift model in `apps/shifts/models.py` has `restaurant` FK, `employee` FK, `date`, `start_time`, `end_time`, `notes`, and `CheckConstraint(end_time > start_time)`
- [ ] T006 [P] Verify migrations exist and are up to date for `apps/shifts/`

**Checkpoint**: Foundation ready — user story verification can now begin in parallel

---

## Phase 3: User Story 1 — Admin Creates and Manages Shifts (Priority: P1) 🎯 MVP

**Goal**: Admin can create, read, update, and delete staff shifts for any employee.

**Independent Test**: Admin can create a shift for a waiter, verify it appears in the shift list, update the time range, and delete it.

### Verification for User Story 1

- [ ] T007 [P] [US1] Verify `ShiftSerializer` in `apps/shifts/serializers.py` includes `employee`, `date`, `start_time`, `end_time`, `notes`, and computed `duration_hours`
- [ ] T008 [P] [US1] Verify `ShiftWriteSerializer` in `apps/shifts/serializers.py` validates `end_time > start_time` in `validate()` method
- [ ] T009 [US1] Verify `create_shift` service in `apps/shifts/services.py` creates Shift with `restaurant_id` from auth, returns created instance
- [ ] T010 [US1] Verify `update_shift` service in `apps/shifts/services.py` updates allowed fields (`employee`, `date`, `start_time`, `end_time`, `notes`) and saves with `update_fields`
- [ ] T011 [US1] Verify `delete_shift` service in `apps/shifts/services.py` deletes the shift instance
- [ ] T012 [US1] Verify `perform_create` in `apps/shifts/views.py` calls `create_shift` with `restaurant_id` from `get_restaurant_id_from_auth()`
- [ ] T013 [US1] Verify `perform_update` in `apps/shifts/views.py` calls `update_shift` with the existing shift instance
- [ ] T014 [US1] Verify `perform_destroy` in `apps/shifts/views.py` calls `delete_shift`
- [ ] T015 [US1] Verify `get_permissions` in `apps/shifts/views.py` returns `[IsAdmin()]` for create, update, delete actions
- [ ] T016 [US1] Verify `Shift.clean()` in `apps/shifts/models.py` rejects non-staff employee roles (customer)

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 — Staff Views Own Schedule (Priority: P1)

**Goal**: Staff users (waiter, cook) can list shifts filtered by date range and/or employee.

**Independent Test**: Staff user authenticates and fetches shifts filtered by `employee_id` (own ID) and date range.

### Verification for User Story 2

- [ ] T017 [P] [US2] Verify `list` in `apps/shifts/views.py` passes `restaurant_id`, optional `date`/`date_from`/`date_to`, and `employee_id` to `list_shifts` selector
- [ ] T018 [P] [US2] Verify `list_shifts` in `apps/shifts/selectors.py` filters by `restaurant_id`, optional date range, and optional `employee__public_id`
- [ ] T019 [US2] Verify `get_permissions` in `apps/shifts/views.py` returns `[IsStaff()]` for `list` and `retrieve` actions
- [ ] T020 [US2] Verify staff user (waiter/cook) receives 403 when attempting POST, PATCH, or DELETE on shifts

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 — Admin Copies Shifts Across Dates (Priority: P2)

**Goal**: Admin can copy an entire day's schedule to one or more future dates.

**Independent Test**: POST to `/api/shifts/copy/` with a source date and multiple target dates, then verify each target date has the same shifts.

### Verification for User Story 3

- [ ] T021 [P] [US3] Verify `copy` action in `apps/shifts/views.py` validates input with `CopyShiftsSerializer`, calls `copy_shifts` service
- [ ] T022 [P] [US3] Verify `CopyShiftsSerializer` in `apps/shifts/serializers.py` accepts `source_date`, `target_dates`, and optional `employee_ids`
- [ ] T023 [US3] Verify `copy_shifts` in `apps/shifts/services.py` uses `get_or_create` per shift, returns total created count
- [ ] T024 [US3] Verify `copy_shifts` raises `IntegrityError` when shift already exists on target date (handled as 409 Conflict in view)
- [ ] T025 [US3] Verify `copy` action filters by `employee_ids` when provided

**Checkpoint**: At this point, User Stories 1, 2, AND 3 should all work independently

---

## Phase 6: User Story 4 — Admin Views Monthly Hour Summary (Priority: P2)

**Goal**: Admin can see total hours per employee for a given month.

**Independent Test**: GET `/api/shifts/month_summary/?year=2026&month=7` returns per-shift breakdown with total hours.

### Verification for User Story 4

- [ ] T026 [P] [US4] Verify `month_summary` action in `apps/shifts/views.py` validates `year` and `month` query params, calls `get_month_summary` selector
- [ ] T027 [P] [US4] Verify `get_month_summary` in `apps/shifts/selectors.py` filters by `restaurant_id`, `date__year`/`date__month`, and optional `employee__public_id`
- [ ] T028 [US4] Verify `month_summary` returns `{"total_hours": <float>, "shifts": [...]}` with `duration_hours` per shift
- [ ] T029 [US4] Verify `month_summary` returns `{"total_hours": 0.0, "shifts": []}` for empty months

**Checkpoint**: All user stories should now be independently functional

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T030 [P] Add tests for Shift CRUD operations in `apps/shifts/tests/test_crud.py`
- [ ] T031 [P] Add tests for shift listing with date range and employee filters in `apps/shifts/tests/test_list.py`
- [ ] T032 [P] Add tests for copy shifts (success, conflict, employee filter) in `apps/shifts/tests/test_copy.py`
- [ ] T033 [P] Add tests for month summary (with data, empty month, employee filter) in `apps/shifts/tests/test_summary.py`
- [ ] T034 [P] Add tests for role-based access (admin vs staff vs customer) in `apps/shifts/tests/test_permissions.py`
- [ ] T035 Add overlap detection warning (FR-013 SHOULD) — service-layer check in `apps/shifts/services.py` when creating/updating a shift
- [ ] T036 [P] Run `ruff` lint on `apps/shifts/` — fix any issues
- [ ] T037 [P] Run `bandit` security checks on `apps/shifts/` — fix any issues
- [ ] T038 Run `quickstart.md` validation scenarios to verify end-to-end behavior

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - US1 (P1) and US2 (P1) can proceed in parallel
  - US3 (P2) and US4 (P2) can proceed after or in parallel with US1/US2
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational — No dependencies on other stories
- **US2 (P1)**: Can start after Foundational — No dependencies on US1
- **US3 (P2)**: Depends on US1 (uses same `create_shift` infrastructure)
- **US4 (P2)**: Depends on US1 (uses same Shift query infrastructure)

### Within Each User Story

- Verification tasks marked [P] can run in parallel
- Core verification before integration verification
- Story complete before moving to next priority

### Parallel Opportunities

- All Foundational tasks marked [P] can run in parallel (Phase 2)
- US1 and US2 verification tasks can run in parallel (different methods/files)
- All tests in Phase 7 marked [P] can run in parallel
- Different user stories can be verified in parallel

---

## Parallel Example: User Story 1

```bash
# Launch all parallel verification for User Story 1:
Task: "Verify ShiftSerializer in apps/shifts/serializers.py"
Task: "Verify ShiftWriteSerializer in apps/shifts/serializers.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup verification
2. Complete Phase 2: Foundational verification (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation verified
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo
5. Add User Story 4 → Test independently → Deploy/Demo
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1
   - Developer B: User Story 2
   - Developer C: User Story 3 & 4
3. Stories complete and integrate independently
