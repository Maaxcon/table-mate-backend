# Feature Specification: Staff Shift Scheduler

**Feature Branch**: `staff-ops/shift-scheduler`
**Created**: 2026-07-27
**Status**: Draft
**Input**: Staff shift scheduler — create, read, update, delete shifts with date-range filtering, monthly hour summaries, and bulk copy across dates. Admin manages all shifts; staff view own schedules.

## User Scenarios & Testing

### User Story 1 — Admin Creates and Manages Shifts (Priority: P1)

As an admin, I can create, read, update, and delete staff shifts for any employee so the restaurant has a complete staff schedule for each day.

**Why this priority**: Core scheduling capability — without CRUD there is no schedule.

**Independent Test**: Admin can create a shift for a waiter, verify it appears in the shift list, update the time range, and delete it.

**Acceptance Scenarios**:

1. **Given** an authenticated admin user, **When** POST to `/api/shifts/` with `employee`, `date`, `start_time`, `end_time`, **Then** a Shift is created and returned with computed `duration_hours`.
2. **Given** an existing shift, **When** PATCH to `/api/shifts/{id}/` with new `end_time`, **Then** the shift is updated with recalculated duration.
3. **Given** an existing shift, **When** DELETE to `/api/shifts/{id}/`, **Then** the shift is removed and subsequent GET returns 404.
4. **Given** `end_time` is before or equal to `start_time`, **When** creating or updating a shift, **Then** a validation error is returned.

---

### User Story 2 — Staff Views Own Schedule (Priority: P1)

As a waiter or cook, I can see my scheduled shifts for a given date range so I know when I'm working.

**Why this priority**: Staff need visibility into their schedule regardless of who manages it.

**Independent Test**: Staff user authenticates and fetches shifts filtered by employee_id (own ID) and date range.

**Acceptance Scenarios**:

1. **Given** an authenticated staff user (waiter or cook), **When** GET `/api/shifts/?employee_id=me&date_from=2026-07-01&date_to=2026-07-31`, **Then** only that employee's shifts are returned.
2. **Given** a waiter, **When** POST to `/api/shifts/` with any data, **Then** a 403 Forbidden is returned.
3. **Given** a cook viewing own shifts, **When** PATCH or DELETE on any shift, **Then** a 403 Forbidden is returned.

---

### User Story 3 — Admin Copies Shifts Across Dates (Priority: P2)

As an admin, I can copy an entire day's schedule to one or more future dates so I don't have to manually re-enter recurring patterns.

**Why this priority**: Schedule patterns repeat weekly; bulk copy saves significant admin time.

**Independent Test**: POST to `/api/shifts/copy/` with a source date and multiple target dates, then verify each target date has the same shifts.

**Acceptance Scenarios**:

1. **Given** shifts exist for Monday July 1, **When** POST `/api/shifts/copy/` with `source_date=2026-07-01`, `target_dates=["2026-07-08", "2026-07-15"]`, **Then** both target dates have identical shifts.
2. **Given** shifts already exist on a target date for the same employee, **When** the copy endpoint is called, **Then** a 409 Conflict is returned without modifying existing data.
3. **Given** `employee_ids=["emp1"]` filter, **When** copying, **Then** only shifts for `emp1` are copied.

---

### User Story 4 — Admin Views Monthly Hour Summary (Priority: P2)

As an admin, I can see total hours per employee for a given month so I can track labor costs and verify payroll.

**Why this priority**: Monthly hour aggregation is needed for payroll and labor reporting.

**Independent Test**: GET `/api/shifts/month_summary/?year=2026&month=7` returns per-shift breakdown with total hours.

**Acceptance Scenarios**:

1. **Given** multiple shifts exist in July 2026 for various employees, **When** GET `/api/shifts/month_summary/?year=2026&month=7`, **Then** a `total_hours` float and `shifts` array with per-shift `duration_hours` is returned.
2. **Given** `employee_id` filter param, **When** requesting month summary, **Then** only that employee's shifts are included.
3. **Given** a month with no shifts, **When** requesting month summary, **Then** `total_hours: 0.0` and empty `shifts` array is returned.

---

### Edge Cases

- Admin attempts to assign a shift to a non-staff user (customer role) — should be rejected with validation error.
- Shift time range spans midnight (e.g., 22:00 - 02:00) — currently treated as same-day; clarify if overnight shifts are in scope.
- Two shifts for the same employee on the same date with overlapping times — no overlap constraint exists currently; potential double-booking.
- Copy to a date where some but not all shifts already exist — entire copy fails; partial success may be preferred.
- Month summary with shifts spanning month boundary — only shifts within the queried month are counted.

## Requirements

### Functional Requirements

- **FR-001**: System MUST allow admin users to create shifts with employee, date, start_time, end_time, and optional notes.
- **FR-002**: System MUST allow admin users to update shift time, date, employee, and notes.
- **FR-003**: System MUST allow admin users to delete shifts.
- **FR-004**: System MUST allow staff users (waiter, cook) to list shifts, filtered by date range and/or employee.
- **FR-005**: System MUST allow admin users to copy all shifts from a source date to one or more target dates.
- **FR-006**: System MUST allow admin users to filter the copy operation to specific employees.
- **FR-007**: System MUST reject copy when target date already has a shift for the same employee.
- **FR-008**: System MUST provide a month summary endpoint returning total hours and per-shift breakdown.
- **FR-009**: System MUST enforce that `end_time > start_time` for every shift.
- **FR-010**: System MUST assign shifts only to staff roles (waiter, cook, admin) — customer role MUST be rejected.
- **FR-011**: System MUST scope shifts to a restaurant — admin/staff only see their own restaurant's schedule.
- **FR-012**: Staff users MUST NOT be able to create, update, or delete shifts.
- **FR-013**: System SHOULD detect and warn on overlapping shifts for the same employee on the same date.
- **FR-014**: System SHOULD support recurring shift templates for weekly schedule patterns.

### Canonical Contract Impact

- **Impacted Entities**: Shift (new entity added to canonical set in constitution v2.1.0)
- **Contract Delta**: No changes to existing entities. Shift is additive.
- **Backend Source of Truth Rule**: Shift CRUD goes through service layer with restaurant scoping.

### Role Access Matrix

- **Admin**: Full CRUD on shifts, copy, month summary.
- **Waiter**: Read-only — can list shifts (own or filtered), cannot create/update/delete.
- **Cook**: Read-only — can list own shifts, cannot create/update/delete.
- **Customer**: No shift access at all.

### Key Entities

- **Shift**: `restaurant`, `employee` (User FK), `date`, `start_time`, `end_time`, `notes`. Computed: `duration_hours`.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Admin creates a shift in under 30 seconds (single form submission).
- **SC-002**: Copying a 20-shift day to 5 target dates completes in under 2 seconds.
- **SC-003**: Month summary for a restaurant with 500 shifts returns in under 500ms.
- **SC-004**: Staff users successfully view their schedule with zero authorization errors when following the intended flow.

## Assumptions

- Shifts are same-day only (start and end on the same calendar date); overnight shifts deferred.
- No overlapping shift detection is enforced at DB level; may be added as service-layer validation.
- Restaurant scoping is always present — no cross-restaurant shift management.
- Employee list is pre-populated via the User model; no separate employee management in this feature scope.
