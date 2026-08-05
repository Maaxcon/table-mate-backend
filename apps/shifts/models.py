from typing import Any

from django.core.exceptions import ValidationError
from django.db import models

from apps.authentication.models import RoleCode, User
from common.models import BaseModel


class Shift(BaseModel):
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        on_delete=models.CASCADE,
        related_name="shifts",
    )
    employee = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="shifts",
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["date", "start_time", "employee_id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="shifts_end_after_start",
            ),
        ]
        indexes = [
            models.Index(fields=["restaurant", "date"]),
            models.Index(fields=["restaurant", "employee", "date"]),
        ]

    def clean(self) -> None:
        if self.employee_id and self.employee.role not in (RoleCode.WAITER, RoleCode.COOK, RoleCode.ADMIN):
            raise ValidationError("Shifts can only be assigned to staff (waiter, cook, or admin).")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.employee} {self.date} {self.start_time}-{self.end_time}"
