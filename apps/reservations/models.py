from django.db import models

from apps.authentication.models import RoleCode
from common.models import RestaurantScopedModel


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
        "orders.Table",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservations",
    )
    guest_count = models.PositiveIntegerField()
    reserved_for = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=ReservationStatus.choices,
        default=ReservationStatus.PENDING,
    )
    notes = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["reserved_for", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=ReservationStatus.values),
                name="reservations_reservation_status_valid",
            )
        ]

    def __str__(self) -> str:
        return f"Reservation {self.public_id}"
