from datetime import date as date_type
from datetime import time as time_type

from django.db import transaction

from apps.authentication.models import User

from .models import Shift


def find_overlapping_shifts(
    restaurant_id: int,
    employee: User,
    date: date_type,
    start_time: time_type,
    end_time: time_type,
    exclude_shift_id: int | None = None,
) -> list[Shift]:
    qs = Shift.objects.filter(
        restaurant_id=restaurant_id,
        employee=employee,
        date=date,
        start_time__lt=end_time,
        end_time__gt=start_time,
    )
    if exclude_shift_id is not None:
        qs = qs.exclude(id=exclude_shift_id)
    return list(qs)


@transaction.atomic
def create_shift(
    *,
    restaurant_id: int,
    employee: User,
    date: date_type,
    start_time: time_type,
    end_time: time_type,
    notes: str = "",
) -> Shift:
    overlaps = find_overlapping_shifts(
        restaurant_id=restaurant_id,
        employee=employee,
        date=date,
        start_time=start_time,
        end_time=end_time,
    )
    if overlaps:
        msg = "This shift overlaps with an existing shift."
        raise ValueError(msg)
    return Shift.objects.create(
        restaurant_id=restaurant_id,
        employee=employee,
        date=date,
        start_time=start_time,
        end_time=end_time,
        notes=notes,
    )


@transaction.atomic
def update_shift(shift: Shift, **data: object) -> Shift:
    allowed = frozenset({"employee", "date", "start_time", "end_time", "notes"})
    changed = [f for f in allowed if f in data]
    if changed:
        employee = data.get("employee", shift.employee)
        date = data.get("date", shift.date)
        start_time = data.get("start_time", shift.start_time)
        end_time = data.get("end_time", shift.end_time)
        overlaps = find_overlapping_shifts(
            restaurant_id=shift.restaurant_id,
            employee=employee,
            date=date,
            start_time=start_time,
            end_time=end_time,
            exclude_shift_id=shift.id,
        )
        if overlaps:
            msg = "This shift overlaps with an existing shift."
            raise ValueError(msg)
    for field in changed:
        setattr(shift, field, data[field])
    if changed:
        shift.save(update_fields=[*changed, "updated_at"])
    return shift


@transaction.atomic
def delete_shift(shift: Shift) -> None:
    shift.delete()


@transaction.atomic
def copy_shifts(
    *,
    restaurant_id: int,
    source_date: date_type,
    target_dates: list[date_type],
    employee_ids: list[str] | None = None,
) -> int:
    """Copy all shifts from source_date to each target_date.
    Overlapping shifts on target dates are silently skipped.
    Returns the total number of shifts created.
    """
    source_shifts = Shift.objects.filter(
        restaurant_id=restaurant_id,
        date=source_date,
    )
    if employee_ids:
        source_shifts = source_shifts.filter(employee__public_id__in=employee_ids)

    total_created = 0
    for target_date in target_dates:
        for shift in source_shifts:
            overlaps = find_overlapping_shifts(
                restaurant_id=restaurant_id,
                employee=shift.employee,
                date=target_date,
                start_time=shift.start_time,
                end_time=shift.end_time,
            )
            if overlaps:
                continue
            _, created = Shift.objects.get_or_create(
                restaurant_id=restaurant_id,
                employee=shift.employee,
                date=target_date,
                start_time=shift.start_time,
                defaults={
                    "end_time": shift.end_time,
                    "notes": shift.notes,
                },
            )
            if created:
                total_created += 1

    return total_created
