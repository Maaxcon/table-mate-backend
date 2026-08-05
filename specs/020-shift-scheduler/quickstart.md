# Quickstart: Staff Shift Scheduler

## Prerequisites

- Docker Compose environment running (`docker compose up -d`)
- Admin user JWT token
- Staff user (waiter/cook) JWT token
- Existing staff users (employees) in the DB

## Validation Scenarios

### Scenario 1: Admin CRUD

```bash
# Create a shift
curl -X POST http://localhost:8000/api/shifts/ \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"employee": "<staff-user-public-id>", "date": "2026-07-27", "start_time": "09:00", "end_time": "17:00"}'

# Expected: 201 with shift object including duration_hours=8.0
```

```bash
# List shifts
curl http://localhost:8000/api/shifts/ \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Expected: 200 with paginated shift list
```

```bash
# Update a shift
curl -X PATCH http://localhost:8000/api/shifts/<shift-id>/ \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"end_time": "18:00"}'

# Expected: 200 with updated shift
```

```bash
# Delete a shift
curl -X DELETE http://localhost:8000/api/shifts/<shift-id>/ \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Expected: 204 No Content
```

### Scenario 2: Staff Read-Only

```bash
# Staff lists own shifts
curl "http://localhost:8000/api/shifts/?employee_id=<staff-public-id>&date_from=2026-07-01&date_to=2026-07-31" \
  -H "Authorization: Bearer $STAFF_TOKEN"

# Expected: 200 with only that employee's shifts
```

```bash
# Staff tries to create a shift (should fail)
curl -X POST http://localhost:8000/api/shifts/ \
  -H "Authorization: Bearer $STAFF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"employee": "<staff-public-id>", "date": "2026-07-27", "start_time": "09:00", "end_time": "17:00"}'

# Expected: 403 Forbidden
```

### Scenario 3: Copy Shifts

```bash
# Create source shifts first, then copy
curl -X POST http://localhost:8000/api/shifts/copy/ \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_date": "2026-07-01", "target_dates": ["2026-07-08", "2026-07-15"]}'

# Expected: 201 with {"copied": <count>}
```

```bash
# Copy with conflict (run same command again)
# Expected: 409 Conflict
```

### Scenario 4: Month Summary

```bash
curl "http://localhost:8000/api/shifts/month_summary/?year=2026&month=7" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Expected: 200 with {"total_hours": <float>, "shifts": [...]}
```

```bash
# Month summary for empty month
curl "http://localhost:8000/api/shifts/month_summary/?year=2025&month=1" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Expected: 200 with {"total_hours": 0.0, "shifts": []}
```

### Scenario 5: Validation

```bash
# end_time <= start_time (should fail)
curl -X POST http://localhost:8000/api/shifts/ \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"employee": "<staff-public-id>", "date": "2026-07-27", "start_time": "17:00", "end_time": "09:00"}'

# Expected: 400 Validation Error
```
