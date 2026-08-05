# Data Model: Staff Shift Scheduler

## Shift

Staff scheduling record for a restaurant.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField (PK) | Primary Key | Internal DB identifier |
| `public_id` | UUIDField | Unique, indexed, default=uuid4 | Public-facing identifier |
| `restaurant` | ForeignKey(Restaurant) | NOT NULL, CASCADE | Restaurant this shift belongs to |
| `employee` | ForeignKey(User) | NOT NULL, CASCADE | Staff member assigned to shift |
| `date` | DateField | NOT NULL | Shift date |
| `start_time` | TimeField | NOT NULL | Shift start time |
| `end_time` | TimeField | NOT NULL | Shift end time |
| `notes` | TextField | blank=True, default="" | Optional notes |
| `created_at` | DateTimeField | auto_now_add | Record creation timestamp |
| `updated_at` | DateTimeField | auto_now | Last update timestamp |

### Constraints

1. **CheckConstraint**: `end_time > start_time` — enforced at DB level.
2. **Index**: `(restaurant, date)` — for date-range queries.
3. **Index**: `(restaurant, employee, date)` — for employee schedule queries.

### Computed Fields (not stored)

- `duration_hours`: `(end_time - start_time) / 60` computed in serializers and selectors.

### Validation Rules

1. `employee.role` must be one of: `waiter`, `cook`, `admin` — enforced in `Shift.clean()`.
2. `end_time > start_time` — enforced by DB `CheckConstraint` and serializer `validate()`.
3. `restaurant_id` is set from JWT auth token on create — never from request body.

### State Transitions

Shift records are mutable (update/delete allowed by admin). No state machine — shift exists as a simple timespan record.

## Relationships

```text
Restaurant (1) ──< (N) Shift
User (1) ──< (N) Shift  (via employee FK, role IN (waiter, cook, admin))
```
