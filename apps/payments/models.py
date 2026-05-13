from django.db import models

from common.models import BaseModel, RestaurantScopedModel


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    AUTHORIZED = "authorized", "Authorized"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"
    REFUNDED = "refunded", "Refunded"
    CANCELLED = "cancelled", "Cancelled"


class Payment(RestaurantScopedModel):
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    provider = models.CharField(max_length=64)
    provider_transaction_id = models.CharField(max_length=255, unique=True)
    amount = models.DecimalField(max_digits=14, decimal_places=4)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    raw_payload = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=PaymentStatus.values),
                name="payments_payment_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"Payment {self.public_id}"


class WebhookEvent(BaseModel):
    provider = models.CharField(max_length=64)
    event_id = models.CharField(max_length=255, unique=True)
    payload = models.JSONField()
    received_at = models.DateTimeField()
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at", "-id"]

    def __str__(self) -> str:
        return f"{self.provider}:{self.event_id}"
