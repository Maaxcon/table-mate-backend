from decimal import Decimal

from django.db import models

from common.models import BaseModel


class PaymentMethod(models.TextChoices):
    CARD = "card", "Card"
    CASH = "cash", "Cash"


class Receipt(BaseModel):
    """A past visit shown in a customer's cabinet history.

    Decoupled from the operational Order/Session models on purpose, so it is
    simple to create and manage by hand in the Django admin.
    """

    customer = models.ForeignKey(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="receipts",
    )
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        on_delete=models.PROTECT,
        related_name="receipts",
    )
    order_number = models.CharField(max_length=40)
    visited_at = models.DateTimeField()
    currency = models.CharField(max_length=3, default="USD")
    table_label = models.CharField(max_length=40, blank=True, default="")
    server_name = models.CharField(max_length=80, blank=True, default="")
    guests = models.PositiveIntegerField(default=1)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    service_charge = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tip = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    payment_method = models.CharField(
        max_length=10,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CARD,
    )
    payment_status = models.CharField(max_length=20, default="Paid")

    class Meta:
        ordering = ["-visited_at", "-id"]

    def __str__(self) -> str:
        return f"{self.order_number} — {self.customer_id}"

    @property
    def subtotal(self) -> Decimal:
        return sum((item.line_total for item in self.items.all()), Decimal("0.00"))

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.tax + self.service_charge + self.tip


class ReceiptItem(BaseModel):
    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=120)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.quantity}× {self.name}"

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity
