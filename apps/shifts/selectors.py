from datetime import date as date_type
from typing import Any

from django.db.models import QuerySet

from apps.authentication.models import RoleCode, User

from .models import Shift


def list_shifts(
    restaurant_id: int,
    *,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
    employee_id: str | None = None,
    date: date_type | None = None,
) -> QuerySet[Shift]:
    qs = Shift.objects.filter(restaurant_id=restaurant_id).select_related("employee")

    if date is not None:
        qs = qs.filter(date=date)
    else:
        if date_from is not None:
            qs = qs.filter(date__gte=date_from)
        if date_to is not None:
            qs = qs.filter(date__lte=date_to)

    if employee_id is not None:
        qs = qs.filter(employee__public_id=employee_id)

    return qs


def get_shift(shift_id: str, restaurant_id: int) -> Shift | None:
    return Shift.objects.filter(
        public_id=shift_id,
        restaurant_id=restaurant_id,
    ).select_related("employee").first()


def list_employees_with_shifts(
    restaurant_id: int,
    date: date_type,
) -> QuerySet[User]:
    """Return staff users who have at least one shift on the given date."""
    return User.objects.filter(
        restaurant_id=restaurant_id,
        shifts__restaurant_id=restaurant_id,
        shifts__date=date,
    ).exclude(role=RoleCode.CUSTOMER).distinct()


def get_month_summary(
    restaurant_id: int,
    year: int,
    month: int,
    employee_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return total shift hours per employee for a given month."""
    qs = Shift.objects.filter(
        restaurant_id=restaurant_id,
        date__year=year,
        date__month=month,
    ).select_related("employee")

    if employee_id is not None:
        qs = qs.filter(employee__public_id=employee_id)

    results: list[dict[str, Any]] = []
    for shift in qs:
        start_minutes = shift.start_time.hour * 60 + shift.start_time.minute
        end_minutes = shift.end_time.hour * 60 + shift.end_time.minute
        duration_hours = (end_minutes - start_minutes) / 60
        results.append({
            "shift_id": str(shift.public_id),
            "employee_id": str(shift.employee.public_id),
            "employee_name": f"{shift.employee.first_name} {shift.employee.last_name}".strip() or shift.employee.email,
            "employee_role": shift.employee.role,
            "date": shift.date.isoformat(),
            "start_time": shift.start_time.isoformat(),
            "end_time": shift.end_time.isoformat(),
            "duration_hours": round(duration_hours, 2),
        })

    return results


def get_employee_month_hours(
    restaurant_id: int,
    employee_id: str,
    year: int,
    month: int,
) -> float:
    """Return total hours for a single employee in a given month."""
    shifts = Shift.objects.filter(
        restaurant_id=restaurant_id,
        employee__public_id=employee_id,
        date__year=year,
        date__month=month,
    )
    total = 0.0
    for shift in shifts:
        start_m = shift.start_time.hour * 60 + shift.start_time.minute
        end_m = shift.end_time.hour * 60 + shift.end_time.minute
        total += (end_m - start_m) / 60
    return round(total, 2)
