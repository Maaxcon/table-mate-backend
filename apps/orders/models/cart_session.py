from django.db import models

from common.models import RestaurantScopedModel


class CartSessionStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    CLOSED = "closed", "Closed"


class CartSession(RestaurantScopedModel):
    reservation = models.ForeignKey(
        "reservations.Reservation",
        on_delete=models.CASCADE,
        related_name="cart_sessions",
    )
    status = models.CharField(
        max_length=20,
        choices=CartSessionStatus.choices,
        default=CartSessionStatus.ACTIVE,
    )
    created_by = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_cart_sessions",
    )
    participants = models.ManyToManyField(
        "authentication.User",
        blank=True,
        related_name="cart_sessions",
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=CartSessionStatus.values),
                name="orders_cartsession_status_valid",
            ),
            models.UniqueConstraint(
                fields=["restaurant", "id"],
                name="orders_cartsession_rest_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"CartSession {self.public_id}"
