# Feature Specification: Staff Shift Scheduler

**Feature Branch**: `staff-ops/shift-scheduler`
**Created**: 2026-07-27
**Status**: Draft
**Input**: Staff shift scheduler — create, read, update, delete shifts with date-range filtering, monthly hour summaries, and bulk copy across dates. Admin manages all shifts; staff view own schedules.

## Clarifications

### Session 2026-07-27

- Q: Who can view the month summary endpoint? → A: Option A — open to all staff (waiter, cook, admin), not just admin.
- Q: What UX detail should the spec include for the staff shift view? → A: Option C — full UX flow specification (page layout, interactions, empty/loading/error states) for all user stories.

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

**UX Specification**:

- **Page**: Admin Schedule Management — dedicated route `/shifts` in the admin navigation.
- **Layout**: Top bar with date picker (single-day view) and optional employee filter dropdown. Below: a shift list grouped by employee (each employee gets a section with their shifts for the selected day).
- **Create flow**: "Add Shift" button opens a modal/panel with employee dropdown, date (pre-filled), time pickers for start/end, and optional notes field. On submit, the new shift appears in the list and a brief success toast is shown.
- **Edit flow**: Click on a shift row opens an inline edit or modal with prepopulated fields. Save updates the row in-place.
- **Delete flow**: Click delete icon on a shift row shows a confirmation dialog ("Delete shift for {employee} on {date}?"). Confirm removes the row and shows a success toast.
- **Validation errors**: Displayed inline on the form fields (end before start, missing fields). Backend 400 errors shown as a top-of-form alert.
- **Empty state**: "No shifts scheduled for this date" with a prompt to create one.
- **Loading state**: Skeleton rows while the shift list loads.
- **Error state**: Banner "Could not load shifts. Try again." with a retry button.

---

### User Story 2 — Staff Views Own Schedule (Priority: P1)

As a waiter or cook, I can see my scheduled shifts for a given date range so I know when I'm working.

**Why this priority**: Staff need visibility into their schedule regardless of who manages it.

**Independent Test**: Staff user authenticates and fetches shifts filtered by employee_id (own ID) and date range.

**Acceptance Scenarios**:

1. **Given** an authenticated staff user (waiter or cook), **When** GET `/api/shifts/?employee_id=me&date_from=2026-07-01&date_to=2026-07-31`, **Then** only that employee's shifts are returned.
2. **Given** a waiter, **When** POST to `/api/shifts/` with any data, **Then** a 403 Forbidden is returned.
3. **Given** a cook viewing own shifts, **When** PATCH or DELETE on any shift, **Then** a 403 Forbidden is returned.

**UX Specification**:

- **Page**: My Schedule — accessible from the staff navigation (waiter/cook sidebar or top nav as "My Schedule" or "Shifts").
- **Layout**: Calendar-month grid view for desktop, single-month scrollable list for mobile. Each day cell shows the authenticated user's shift times (e.g., "09:00–17:00") and a marker (dot) on days they are scheduled. Current day is highlighted. Selecting a day opens a **day-detail panel** below the calendar.
- **Day-detail panel (team roster)**: Shows the full roster for the selected day — every employee's name, role, and shift hours, fetched from the restaurant-wide shift list for that date (no `employee_id` filter). The authenticated user's own row is highlighted and labeled "(You)". This team roster is intended: staff can see who else is working on a given day, while the calendar grid itself stays scoped to their own shifts.
- **Navigation**: Date range picker or prev/next month arrows. Default view loads the current month on entry.
- **Filter behavior**: The calendar-month grid filters to the authenticated user's shifts on load (derived from JWT — no manual `employee_id` selection). A "show all" toggle is NOT available for waiter/cook; the team roster is reachable only via the day-detail panel for a single selected day, not as a month-wide view.
- **Shift card detail**: Tapping/clicking a shift card expands to show employee name, date, start_time, end_time, duration_hours, notes.
- **Permissions enforcement**: No create/edit/delete UI elements are rendered for waiter/cook. The page is read-only. If the user navigates directly to a shift-edit URL, the frontend should redirect to the list view. Admin users on this page see the Admin Schedule Management page instead.
- **Empty state**: "No shifts scheduled for this month" with a calendar icon illustration.
- **Loading state**: Month grid skeleton with 7-column placeholder cells.
- **Error state**: Banner "Could not load your schedule. Check your connection." with retry button.
- **Role-aware display**: Waiter and cook see the same layout. Admin never sees this view — admin uses the management page (US1).

---

### User Story 3 — Admin Copies Shifts Across Dates (Priority: P2)

As an admin, I can copy an entire day's schedule to one or more future dates so I don't have to manually re-enter recurring patterns.

**Why this priority**: Schedule patterns repeat weekly; bulk copy saves significant admin time.

**Independent Test**: POST to `/api/shifts/copy/` with a source date and multiple target dates, then verify each target date has the same shifts.

**Acceptance Scenarios**:

1. **Given** shifts exist for Monday July 1, **When** POST `/api/shifts/copy/` with `source_date=2026-07-01`, `target_dates=["2026-07-08", "2026-07-15"]`, **Then** both target dates have identical shifts.
2. **Given** shifts already exist on a target date for the same employee, **When** the copy endpoint is called, **Then** a 409 Conflict is returned without modifying existing data.
3. **Given** `employee_ids=["emp1"]` filter, **When** copying, **Then** only shifts for `emp1` are copied.

**UX Specification**:

- **Trigger**: "Copy Schedule" button on the Admin Schedule Management page (US1) toolbar.
- **Flow**: Opens a modal with fields: source date (date picker), target dates (multi-date picker or text field accepting comma-separated dates), optional employee filter (multi-select dropdown). "Copy" button is disabled until source and at least one target date are set.
- **Success**: Modal closes, success toast "Copied {n} shifts to {m} date(s)". The target dates are visually highlighted in the schedule view.
- **Conflict**: If shifts already exist, a 409 error is shown inline in the modal: "Some shifts already exist on {date}. Copy cancelled." The modal stays open so the user can adjust.
- **Loading state**: Copy button shows a spinner during the request. All modal inputs are disabled during processing.
- **Progress indication**: For large copies (many targets), show "Copying... {n} of {m} dates processed" note (if backend supports batch reporting).

---

### User Story 4 — Monthly Hour Summary (Priority: P2)

As a staff member (admin, waiter, or cook), I can see total hours per employee for a given month so I can track labor costs and verify payroll. Staff see all employees' totals (role-scoped to same restaurant).

**Why this priority**: Monthly hour aggregation is needed for payroll and labor reporting.

**Independent Test**: Authenticated user (any staff role) GET `/api/shifts/month_summary/?year=2026&month=7` returns per-shift breakdown with total hours.

**Acceptance Scenarios**:

1. **Given** multiple shifts exist in July 2026 for various employees, **When** GET `/api/shifts/month_summary/?year=2026&month=7`, **Then** a `total_hours` float and `shifts` array with per-shift `duration_hours` is returned.
2. **Given** `employee_id` filter param, **When** requesting month summary, **Then** only that employee's shifts are included.
3. **Given** a month with no shifts, **When** requesting month summary, **Then** `total_hours: 0.0` and empty `shifts` array is returned.
4. **Given** a waiter or cook user, **When** GET `/api/shifts/month_summary/?year=2026&month=7`, **Then** the same aggregated data is returned as for an admin.

**UX Specification**:

- **Page**: Month Summary — accessible from the admin navigation as "Hours Summary" and from the staff navigation as "My Hours".
- **Layout**: Table with columns: employee name, total hours, shift count. Sorting by hours (descending by default). A month/year selector in the page header.
- **Admin view**: Shows all employees in the restaurant. Clicking an employee row expands to show per-shift breakdown (date, start, end, duration).
- **Staff view** (waiter/cook): Shows only their own row with their total hours and shift breakdown. Same table component, pre-filtered.
- **Empty state**: "No shifts recorded for this month" with an empty table placeholder.
- **Loading state**: Table skeleton with 5 placeholder rows.
- **Error state**: "Failed to load month summary. Retry." with retry button.
- **Navigation**: From My Schedule (US2), a link/button "View Month Summary" takes the user here with the current month pre-selected.

---

### Edge Cases

- Admin attempts to assign a shift to a non-staff user (customer role) — should be rejected with validation error.
- Shift time range spans midnight (e.g., 22:00 - 02:00) — currently treated as same-day; clarify if overnight shifts are in scope.
- Two shifts for the same employee on the same date with overlapping times — no overlap constraint exists currently; potential double-booking.
- Copy to a date where some but not all shifts already exist — entire copy fails; partial success may be preferred.
- Month summary with shifts spanning month boundary — only shifts within the queried month are counted.
- Staff user navigates to `/shifts` directly — admin-only routes should redirect staff to "My Schedule" or show a 403 page.
- Admin user navigates to "My Schedule" route — should redirect to the admin management page `/shifts`.
- Browser refresh on a date-filtered list — selected date range persists in URL query params (`?date=...`) so refresh preserves view.
- Shift created by another admin in real-time — the page does NOT auto-refresh; admin should refresh manually or via WebSocket if supported.
- Network failure during shift create/edit/delete — form data is not saved; user must retry. No offline mode.

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
- **FR-015**: Frontend MUST provide an admin schedule management page at `/shifts` with date/employee filtering, CRUD modals, and role enforcement.
- **FR-016**: Frontend MUST provide a staff "My Schedule" page showing the authenticated user's shifts in a calendar-month layout (available to waiter/cook only), with a day-detail panel listing the full team roster for the selected day.
- **FR-017**: Frontend MUST provide a "Month Summary" page (all employees for admin, self-only for waiter/cook) with sortable table and month selector.
- **FR-018**: Frontend MUST enforce role-based UI rendering — waiter/cook see no create/edit/delete controls; admin sees the full management page, not the "My Schedule" view.
- **FR-019**: Frontend MUST handle and display empty, loading, and error states for all shift-related pages as specified in the UX sections below.

### Canonical Contract Impact

- **Impacted Entities**: Shift (new entity added to canonical set in constitution v2.1.0)
- **Contract Delta**: No changes to existing entities. Shift is additive.
- **Backend Source of Truth Rule**: Shift CRUD goes through service layer with restaurant scoping.

### Role Access Matrix

- **Admin**: Full CRUD on shifts, copy, month summary.
- **Waiter**: Read-only — can list shifts for a date range and/or employee (including the restaurant-wide day roster for the My Schedule panel), can view month summary for all employees, cannot create/update/delete.
- **Cook**: Read-only — same as waiter: can list shifts for a date range and/or employee (including the restaurant-wide day roster), can view month summary for all employees, cannot create/update/delete.
- **Customer**: No shift access at all.

### Key Entities

- **Shift**: `restaurant`, `employee` (User FK), `date`, `start_time`, `end_time`, `notes`. Computed: `duration_hours`.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Admin creates a shift in under 30 seconds (single form submission).
- **SC-002**: Copying a 20-shift day to 5 target dates completes in under 2 seconds.
- **SC-003**: Month summary for a restaurant with 500 shifts returns in under 500ms.
- **SC-004**: Staff users successfully view their schedule with zero authorization errors when following the intended flow.
- **SC-005**: Admin schedule management page loads and renders a 20-shift day in under 2 seconds on a mid-range device.
- **SC-006**: Staff "My Schedule" calendar month with 30 shifts renders in under 1.5 seconds on a mid-range device.
- **SC-007**: All shift pages display correct empty, loading, and error states — verified by state-injection tests.

## Assumptions

- Shifts are same-day only (start and end on the same calendar date); overnight shifts deferred.
- No overlapping shift detection is enforced at DB level; may be added as service-layer validation.
- Restaurant scoping is always present — no cross-restaurant shift management.
- Employee list is pre-populated via the User model; no separate employee management in this feature scope.
