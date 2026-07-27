# Shift Management Contract

## Endpoints

All endpoints are scoped to `/api/shifts/` and require authentication.

### CRUD

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/shifts/` | IsStaff | List shifts (filtered by `date`, `date_from`, `date_to`, `employee_id`) |
| POST | `/api/shifts/` | IsAdmin | Create a shift |
| GET | `/api/shifts/{id}/` | IsStaff | Retrieve a single shift |
| PATCH | `/api/shifts/{id}/` | IsAdmin | Partial update a shift |
| DELETE | `/api/shifts/{id}/` | IsAdmin | Delete a shift |

### Custom Actions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/shifts/copy/` | IsAdmin | Copy shifts from source date to target dates |
| GET | `/api/shifts/month_summary/` | IsStaff | Monthly hour summary with per-shift breakdown |

## Shift Entity (API Shape)

### Read Response (GET, LIST)

```json
{
  "public_id": "uuid-string",
  "employee": "employee-public-id",
  "employee_name": "Full Name",
  "employee_role": "waiter",
  "date": "2026-07-27",
  "start_time": "09:00:00",
  "end_time": "17:00:00",
  "notes": "",
  "duration_hours": 8.0,
  "created_at": "2026-07-27T12:00:00Z",
  "updated_at": "2026-07-27T12:00:00Z"
}
```

### Write Payload (POST, PATCH)

```json
{
  "employee": "employee-public-id",
  "date": "2026-07-27",
  "start_time": "09:00:00",
  "end_time": "17:00:00",
  "notes": ""
}
```

### Copy Payload

```json
{
  "source_date": "2026-07-01",
  "target_dates": ["2026-07-08", "2026-07-15"],
  "employee_ids": ["emp1-uuid"]
}
```

### Month Summary Response

```json
{
  "total_hours": 168.5,
  "shifts": [
    {
      "shift_id": "uuid",
      "employee_id": "uuid",
      "employee_name": "Name",
      "employee_role": "waiter",
      "date": "2026-07-01",
      "start_time": "09:00:00",
      "end_time": "17:00:00",
      "duration_hours": 8.0
    }
  ]
}
```

## Role Permissions

| Role | List | Retrieve | Create | Update | Delete | Copy | Month Summary |
|------|------|----------|--------|--------|--------|------|---------------|
| Admin | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Waiter | ✅ (own) | ✅ (own) | ❌ | ❌ | ❌ | ❌ | ❌ |
| Cook | ✅ (own) | ✅ (own) | ❌ | ❌ | ❌ | ❌ | ❌ |
| Customer | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

## Errors

| HTTP Status | Condition |
|-------------|-----------|
| 400 | Validation error (e.g., `end_time <= start_time`, missing params) |
| 403 | Insufficient role permissions |
| 404 | Shift not found |
| 409 | Copy conflict (shift already exists on target date for same employee) |
