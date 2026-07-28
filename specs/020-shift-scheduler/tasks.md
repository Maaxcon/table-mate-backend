# Tasks: Staff Shift Scheduler

**Input**: Design documents from `specs/020-shift-scheduler/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Test tasks are included where the spec or constitution mandates them. Role-based access and API contract compliance are in scope.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 [P] Verify `apps/shifts/` app is registered in Django `INSTALLED_APPS` and migrations applied
- [x] T002 [P] Verify `apps/shifts/urls.py` is included in project root URL configuration
- [x] T003 Verify frontend project has routing infrastructure for `/shifts` (admin) and `/my-schedule` (staff) routes

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be verified

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 [P] Verify `RestaurantScopedViewSetMixin` in `common/api/__init__.py` provides `get_restaurant_id()` via `get_restaurant_id_from_auth()`
- [x] T005 [P] Verify `ShiftViewSet` in `apps/shifts/views.py` uses `get_restaurant_id_from_auth()` in `list`, `perform_create`, `copy`, and `month_summary`
- [x] T006 [P] Verify Shift model in `apps/shifts/models.py` has `restaurant` FK, `employee` FK, `date`, `start_time`, `end_time`, `notes`, and `CheckConstraint(end_time > start_time)`
- [x] T007 [P] Verify migrations exist and are up to date for `apps/shifts/`
- [x] T008 Verify frontend auth guard enforces role-based route access: admin-only routes vs staff-only routes

**Checkpoint**: Foundation ready — user story implementation can now begin in parallel

---

## Phase 3: User Story 1 — Admin Creates and Manages Shifts (Priority: P1) 🎯 MVP

**Goal**: Admin can create, read, update, and delete staff shifts for any employee.

**Independent Test**: Admin can create a shift for a waiter, verify it appears in the shift list, update the time range, and delete it.

### Backend Verification

- [x] T009 [P] [US1] Verify `ShiftSerializer` in `apps/shifts/serializers.py` includes `employee`, `date`, `start_time`, `end_time`, `notes`, and computed `duration_hours`
- [x] T010 [P] [US1] Verify `ShiftWriteSerializer` in `apps/shifts/serializers.py` validates `end_time > start_time` in `validate()` method
- [x] T011 [US1] Verify `create_shift` service in `apps/shifts/services.py` creates Shift with `restaurant_id` from auth
- [x] T012 [US1] Verify `update_shift` service in `apps/shifts/services.py` updates allowed fields and saves with `update_fields`
- [x] T013 [US1] Verify `delete_shift` service in `apps/shifts/services.py` deletes the shift instance
- [x] T014 [US1] Verify `get_permissions` in `apps/shifts/views.py` returns `[IsAdmin()]` for create, update, delete actions
- [x] T015 [US1] Verify `Shift.clean()` in `apps/shifts/models.py` rejects non-staff employee roles (customer)

### Frontend Implementation

- [x] T016 [P] [US1] Create admin shift schedule page at frontend route `/shifts` with date picker and employee filter
- [x] T017 [P] [US1] Build shift list component grouped by employee for the selected date
- [x] T018 [US1] Build "Add Shift" modal with employee dropdown, date picker, start/end time pickers, notes field
- [x] T019 [US1] Build inline edit or edit-modal for existing shifts with prepopulated fields
- [x] T020 [P] [US1] Build delete confirmation dialog for shift removal
- [x] T021 [US1] Integrate shift CRUD with backend API — create, list, update, delete
- [x] T022 [US1] Handle inline validation errors (end before start) and backend 400 responses
- [x] T023 [US1] Implement empty state ("No shifts scheduled"), loading state (skeleton rows), and error state with retry
- [x] T024 [US1] Add success/error toast notifications for create, update, delete operations

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 — Staff Views Own Schedule (Priority: P1)

**Goal**: Staff users (waiter, cook) can see their scheduled shifts in a calendar-month view.

**Independent Test**: Staff user authenticates and sees only their own shifts for the current month in a calendar layout.

### Backend Verification

- [x] T025 [P] [US2] Verify `list` in `apps/shifts/views.py` passes `restaurant_id`, date range, and `employee_id` to `list_shifts`
- [x] T026 [P] [US2] Verify `list_shifts` in `apps/shifts/selectors.py` filters by `restaurant_id`, date range, and `employee__public_id`
- [x] T027 [US2] Verify `get_permissions` in `apps/shifts/views.py` returns `[IsStaff()]` for `list` and `retrieve` actions
- [x] T028 [US2] Verify staff user (waiter/cook) receives 403 when attempting POST, PATCH, or DELETE

### Frontend Implementation

- [x] T029 [P] [US2] Create "My Schedule" page at frontend route `/my-schedule` with calendar-month grid layout
- [x] T030 [P] [US2] Build month navigation (prev/next arrows, month/year display) with current month default
- [x] T031 [US2] Build shift card/cell component showing start-end times within each day cell
- [x] T032 [US2] Implement expandable shift detail (employee name, date, start/end, duration, notes)
- [x] T033 [US2] Fetch shifts filtered to authenticated user (derive employee_id from JWT, no manual filter)
- [x] T034 [US2] Ensure no create/edit/delete UI is rendered for waiter/cook roles — read-only layout
- [x] T035 [US2] Implement empty state ("No shifts this month"), loading skeleton (7-column grid), error state with retry
- [-] T036 [US2] ~~Add link/button "View Month Summary" navigating to month summary page~~ **SKIPPED** — month summary page is admin-only; staff don't need a nav link
- [x] T037 [US2] Add role-based redirect: admin navigating to `/my-schedule` redirects to `/shifts`

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 — Admin Copies Shifts Across Dates (Priority: P2)

**Goal**: Admin can copy an entire day's schedule to one or more future dates.

**Independent Test**: POST to `/api/shifts/copy/` with source date and target dates, verify target dates have identical shifts.

### Backend Verification

- [x] T038 [P] [US3] Verify `copy` action in `apps/shifts/views.py` validates input with `CopyShiftsSerializer`, calls `copy_shifts`
- [x] T039 [P] [US3] Verify `CopyShiftsSerializer` in `apps/shifts/serializers.py` accepts `source_date`, `target_dates`, optional `employee_ids`
- [x] T040 [US3] Verify `copy_shifts` in `apps/shifts/services.py` uses `get_or_create` per shift, returns total count
- [x] T041 [US3] Verify `copy_shifts` raises `IntegrityError` when shift already exists (handled as 409)
- [x] T042 [US3] Verify `copy` action filters by `employee_ids` when provided

### Frontend Implementation

- [x] T043 [P] [US3] Build "Copy Schedule" button on admin schedule management page toolbar
- [x] T044 [US3] Build copy modal with source date picker, multi-target date picker, optional employee multi-select
- [x] T045 [US3] Handle success flow: modal closes, toast "Copied N shifts to M date(s)" shown
- [x] T046 [US3] Handle 409 conflict: inline error in modal, modal stays open for adjustments
- [x] T047 [US3] Implement loading state: spinner on copy button, inputs disabled during request

**Checkpoint**: At this point, User Stories 1, 2, AND 3 should all work independently

---

## Phase 6: User Story 4 — Monthly Hour Summary (Priority: P2)

**Goal**: Staff members can see total hours per employee for a given month.

**Independent Test**: Authenticated user (any staff role) GET `/api/shifts/month_summary/?year=2026&month=7` returns breakdown.

### Backend Verification

- [x] T048 [P] [US4] Verify `month_summary` action in `apps/shifts/views.py` validates `year`/`month` query params, calls `get_month_summary`
- [x] T049 [P] [US4] Verify `get_month_summary` in `apps/shifts/selectors.py` filters by `restaurant_id`, `date__year`/`date__month`, optional `employee__public_id`
- [x] T050 [US4] Verify `month_summary` returns `{"total_hours": <float>, "shifts": [...]}` with `duration_hours` per shift
- [x] T051 [US4] Verify `month_summary` returns `{"total_hours": 0.0, "shifts": []}` for empty months
- [x] T052 [US4] Verify `get_permissions` allows `IsStaff` for `month_summary` action — waiter/cook can access

### Frontend Implementation

- [x] T053 [P] [US4] Create Month Summary page at frontend route `/hours-summary` with month/year selector
- [x] T054 [P] [US4] Build sortable table component: employee name, total hours, shift count columns
- [x] T055 [US4] Build expandable row showing per-shift breakdown (date, start, end, duration)
- [x] T056 [US4] Implement role-aware filtering: admin sees all employees, waiter/cook see only their own row
- [x] T057 [US4] Implement empty state ("No shifts recorded"), loading table skeleton, error state with retry
- [x] T058 [US4] Pre-select current month on navigation from My Schedule link/button

**Checkpoint**: All user stories should now be independently functional

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T059 [P] Add backend tests for Shift CRUD operations in `apps/shifts/tests/test_crud.py`
- [x] T060 [P] Add backend tests for shift listing with date range and employee filters in `apps/shifts/tests/test_list.py`
- [x] T061 [P] Add backend tests for copy shifts (success, conflict, employee filter) in `apps/shifts/tests/test_copy.py`
- [x] T062 [P] Add backend tests for month summary (with data, empty, employee filter) in `apps/shifts/tests/test_summary.py`
- [x] T063 [P] Add backend tests for role-based access (admin vs staff vs customer) in `apps/shifts/tests/test_permissions.py`
- [x] T064 Add overlap detection warning (FR-013 SHOULD) — wired in `ShiftWriteSerializer.validate()` for create/update, in `copy_shifts` service for copy; covered by T073–T075 tests
- [x] T065 [P] Run `ruff` lint on `apps/shifts/` — fix any issues
- [x] T066 [P] Run `bandit` security checks on `apps/shifts/` — fix any issues
- [x] T067 Run `quickstart.md` validation scenarios to verify end-to-end backend behavior
- [x] T068 Verify frontend URL query param persistence for date-filtered admin schedule page
- [x] T069 Verify frontend role-based redirect edge cases (admin→shifts, staff→my-schedule, customer→home)
- [x] T073 [P] Add backend tests for overlap detection on create (same employee, same date, overlapping times → 400)
- [x] T074 [P] Add backend tests for overlap detection on update (PATCH start_time causing overlap → 400; PATCH notes without time fields → allowed)
- [x] T075 [P] Add backend tests for overlap detection during copy (overlapping shifts skipped, partial overlap skipped, multi-employee partial skip)
- [ ] T070 [P] Add frontend unit tests for shift list, calendar grid, summary table components
- [ ] T071 [P] Add frontend integration test for full shift CRUD flow
- [ ] T072 [P] Add frontend integration test for staff schedule calendar flow

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
- **US3 (P2)**: Depends on US1 (uses same create_shift infrastructure and admin page)
- **US4 (P2)**: Depends on US2 (staff routes), shares backend selectors with US1

### Within Each User Story

- Backend verification tasks marked [P] can run in parallel
- Frontend implementation tasks marked [P] can run in parallel
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel
- US1 and US2 can be worked on in parallel by different developers (different pages, different concerns)
- Within US1: backend verification and frontend implementation can proceed in parallel
- US3 and US4 rely on US1/US2 completion but their frontend can be spec'd out in parallel
- All tests in Phase 7 marked [P] can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch all backend verification for User Story 1:
Task: "Verify ShiftSerializer in apps/shifts/serializers.py"
Task: "Verify ShiftWriteSerializer in apps/shifts/serializers.py"

# Launch all frontend implementation for User Story 1 in parallel:
Task: "Create admin shift schedule page at /shifts"
Task: "Build shift list component grouped by employee"
Task: "Build Add Shift modal with employee and time pickers"
```

## Parallel Example: User Story 2

```bash
# Launch all backend verification for User Story 2:
Task: "Verify list view uses list_shifts selector"
Task: "Verify IsStaff permission for list/retrieve"

# Launch all frontend implementation for User Story 2:
Task: "Create My Schedule page with calendar-month grid"
Task: "Build month navigation with prev/next arrows"
Task: "Build shift card component with expandable detail"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup verification
2. Complete Phase 2: Foundational verification (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1 (backend verification + admin frontend page)
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation verified
2. Add User Story 1 → Test independently → Deploy/Demo (MVP — admin CRUD + admin page)
3. Add User Story 2 → Test independently → Deploy/Demo (staff schedule view added)
4. Add User Story 3 → Test independently → Deploy/Demo (copy functionality added)
5. Add User Story 4 → Test independently → Deploy/Demo (month summary added)
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With two developers (backend + frontend):

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Backend Dev: Verify US1–US4 backend tasks
   - Frontend Dev: Implement US1 admin page
3. After backend verification:
   - Backend Dev: Polish, tests, lint
   - Frontend Dev: Continue US2–US4 frontend
4. Stories complete and integrate independently
