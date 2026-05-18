from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.contrib.postgres.fields.ranges import RangeBoundary
from django.db import models
from django.db.models import F, Func, Q

from apps.authentication.models import RoleCode
from common.models import RestaurantScopedModel


class TsTzRange(Func):
    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class ReservationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    CANCELLED = "cancelled", "Cancelled"
    COMPLETED = "completed", "Completed"


class Reservation(RestaurantScopedModel):
    customer = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservations",
        limit_choices_to={"role": RoleCode.CUSTOMER},
    )
    table = models.ForeignKey(
        "restaurants.Table",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservations",
    )
    guest_count = models.PositiveIntegerField()
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=ReservationStatus.choices,
        default=ReservationStatus.PENDING,
    )
    notes = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["start_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=ReservationStatus.values),
                name="reservations_reservation_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(end_at__gt=F("start_at")),
                name="reservations_reservation_end_after_start",
            ),
            ExclusionConstraint(
                name="reservations_no_overlap_per_table",
                expressions=[
                    (
                        TsTzRange(
                            F("start_at"),
                            F("end_at"),
                            RangeBoundary(),
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                    ("table", RangeOperators.EQUAL),
                ],
                condition=Q(status=ReservationStatus.CONFIRMED),
            ),
        ]

    def __str__(self) -> str:
        return f"Reservation {self.public_id}"
