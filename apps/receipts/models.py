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
    # Traceability to the source order/payment. Nullable so receipts can also
    # be created by hand in the admin (e.g. for seeding or corrections).
    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receipt",
    )
    payment = models.ForeignKey(
        "payments.Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receipts",
    )
    order_number = models.CharField(max_length=40)
    visited_at = models.DateTimeField()
    currency = models.CharField(max_length=3, default="UAH")
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
    # Optional link to a real dish from the restaurant's menu. Name and price
    # are snapshotted below so the receipt stays correct even if the menu changes.
    menu_item = models.ForeignKey(
        "menu.MenuItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receipt_items",
    )
    name = models.CharField(max_length=120, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    # Nullable so an unset price (None) can be auto-filled from the menu while a
    # deliberate 0.00 (a comped or genuinely free item) is preserved.
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )

    class Meta:
        ordering = ["id"]

    def save(self, *args: object, **kwargs: object) -> None:
        # Copy name/price from the chosen menu item when left unset. Only None
        # (never provided) is auto-filled — a 0.00 stays free on purpose.
        if self.menu_item is not None:
            if not self.name:
                self.name = self.menu_item.name
            if self.unit_price is None:
                self.unit_price = Decimal(self.menu_item.price).quantize(Decimal("0.01"))
        # Never persist NULL: an item with no menu item and no price is free.
        if self.unit_price is None:
            self.unit_price = Decimal("0.00")
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    def __str__(self) -> str:
        return f"{self.quantity}× {self.name}"

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity
