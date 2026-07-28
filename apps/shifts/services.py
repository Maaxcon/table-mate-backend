from datetime import date as date_type

from django.db import transaction

from apps.authentication.models import User

from .models import Shift


def find_overlapping_shifts(
    restaurant_id: int,
    employee: User,
    date: date_type,
    start_time: str,
    end_time: str,
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
    start_time: str,
    end_time: str,
    notes: str = "",
) -> Shift:
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
            Shift.objects.get_or_create(
                restaurant_id=restaurant_id,
                employee=shift.employee,
                date=target_date,
                start_time=shift.start_time,
                defaults={
                    "end_time": shift.end_time,
                    "notes": shift.notes,
                },
            )
            total_created += 1

    return total_created
