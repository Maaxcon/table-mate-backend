from datetime import time as time_cls
from typing import Any

from django.db.models import QuerySet
from rest_framework import serializers

from apps.authentication.models import RoleCode, User
from apps.restaurants.selectors import get_working_hours_for_date
from common.api import PublicIdRelatedField, get_restaurant_id_from_auth

from .models import Shift
from .services import find_overlapping_shifts


class _EmployeeSlugField(PublicIdRelatedField[User]):
    def get_queryset(self) -> QuerySet[User]:
        request = self.context.get("request")
        user = request.user if request else None
        qs = User.objects.all()
        if user and user.restaurant_id:
            qs = qs.filter(restaurant_id=user.restaurant_id)
        return qs.exclude(role=RoleCode.CUSTOMER)


class ShiftSerializer(serializers.ModelSerializer[Shift]):
    employee = _EmployeeSlugField()
    employee_name = serializers.SerializerMethodField()
    employee_role = serializers.SerializerMethodField()
    duration_hours = serializers.SerializerMethodField()

    class Meta:
        model = Shift
        fields = [
            "public_id",
            "employee",
            "employee_name",
            "employee_role",
            "date",
            "start_time",
            "end_time",
            "notes",
            "duration_hours",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]

    def get_employee_name(self, obj: Shift) -> str:
        name = f"{obj.employee.first_name} {obj.employee.last_name}".strip()
        return name or obj.employee.email

    def get_employee_role(self, obj: Shift) -> str:
        return obj.employee.role

    def get_duration_hours(self, obj: Shift) -> float:
        start_m = obj.start_time.hour * 60 + obj.start_time.minute
        end_m = obj.end_time.hour * 60 + obj.end_time.minute
        return round((end_m - start_m) / 60, 2)


class ShiftWriteSerializer(serializers.ModelSerializer[Shift]):
    employee = _EmployeeSlugField()

    class Meta:
        model = Shift
        fields = [
            "public_id",
            "employee",
            "date",
            "start_time",
            "end_time",
            "notes",
        ]
        read_only_fields = ["public_id"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        start_time = attrs.get("start_time")
        end_time = attrs.get("end_time")
        date = attrs.get("date")
        employee = attrs.get("employee")

        if self.instance is not None:
            start_time = start_time or self.instance.start_time
            end_time = end_time or self.instance.end_time
            date = date or self.instance.date
            employee = employee or self.instance.employee

        if start_time is not None and end_time is not None and end_time <= start_time:
            raise serializers.ValidationError("end_time must be after start_time.")

        request = self.context.get("request")
        if request is not None and date is not None and start_time is not None and end_time is not None:
            restaurant_id = get_restaurant_id_from_auth(request)
            if restaurant_id is not None:
                hours = get_working_hours_for_date(restaurant_id, date)
                if hours is not None:
                    open_str, close_str = hours
                    if open_str < close_str:
                        open_h, open_m = map(int, open_str.split(":"))
                        close_h, close_m = map(int, close_str.split(":"))
                        open_time = time_cls(open_h, open_m)
                        close_time = time_cls(close_h, close_m)
                        if start_time < open_time or end_time > close_time:
                            raise serializers.ValidationError(
                                f"Shift must be within working hours ({open_str}–{close_str})."
                            )

        if employee is not None and date is not None and start_time is not None and end_time is not None:
            restaurant_id = get_restaurant_id_from_auth(request) if request else None
            if restaurant_id is not None:
                overlaps = find_overlapping_shifts(
                    restaurant_id=restaurant_id,
                    employee=employee,
                    date=date,
                    start_time=start_time,
                    end_time=end_time,
                    exclude_shift_id=self.instance.id if self.instance else None,
                )
                if overlaps:
                    raise serializers.ValidationError(
                        "This shift overlaps with an existing shift."
                    )

        return attrs


class CopyShiftsSerializer(serializers.Serializer[Any]):
    source_date = serializers.DateField()
    target_dates = serializers.ListField(child=serializers.DateField())
    employee_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
    )


class ShiftListQuerySerializer(serializers.Serializer[Any]):
    date = serializers.DateField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    employee_id = serializers.UUIDField(required=False)


class MonthSummaryQuerySerializer(serializers.Serializer[Any]):
    year = serializers.IntegerField()
    month = serializers.IntegerField()
    employee_id = serializers.UUIDField(required=False)


class BatchShiftSerializer(serializers.Serializer[Any]):
    shifts = ShiftWriteSerializer(many=True)


class MonthSummarySerializer(serializers.Serializer[Any]):
    total_hours = serializers.FloatField()
    shifts = serializers.ListField(child=serializers.DictField())
