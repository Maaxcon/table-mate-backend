from decimal import Decimal
from typing import Any

from django.db import models, transaction
from django.utils import timezone

from common.models import RestaurantScopedModel

from .cart_item import CartItem as CartItem
from .cart_session import CartSession as CartSession
from .cart_session import CartSessionStatus as CartSessionStatus


class SessionStatus(models.TextChoices):
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"
    VOIDED = "voided", "Voided"


class OrderSource(models.TextChoices):
    WAITER_MANUAL = "waiter_manual", "Waiter manual"
    CUSTOMER_PREPAID = "customer_prepaid", "Customer prepaid"


class OrderStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class OrderPaymentStatus(models.TextChoices):
    UNPAID = "unpaid", "Unpaid"
    AUTHORIZED = "authorized", "Authorized"
    PAID = "paid", "Paid"
    SETTLED = "settled", "Settled"
    REFUNDED = "refunded", "Refunded"
    CANCELLED = "cancelled", "Cancelled"


class TicketStatus(models.TextChoices):
    INCOMING = "incoming", "Incoming"
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    BUMPED = "bumped", "Bumped"


class OrderItemStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    IN_PROGRESS = "in_progress", "In progress"
    READY = "ready", "Ready"
    SERVED = "served", "Served"
    VOIDED = "voided", "Voided"


class CreatedBySource(models.TextChoices):
    STAFF = "staff", "Staff"
    CUSTOMER = "customer", "Customer"
    SYSTEM = "system", "System"


class VoidReason(models.Model):
    code = models.CharField(max_length=32, unique=True)
    label = models.CharField(max_length=64)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.label


class Session(RestaurantScopedModel):
    table = models.ForeignKey(
        "restaurants.Table",
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    reservation = models.OneToOneField(
        "reservations.Reservation",
        on_delete=models.PROTECT,
        related_name="session",
    )
    opened_by = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opened_sessions",
    )
    guest_count = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=SessionStatus.choices, default=SessionStatus.OPEN)
    currency = models.CharField(max_length=3)
    subtotal = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    tax = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    service_charge = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    opened_at = models.DateTimeField()

    class Meta:
        ordering = ["-opened_at", "-id"]
        indexes = [
            models.Index(
                fields=["restaurant", "table"],
                name="ord_sess_rest_tbl_open_idx",
                condition=models.Q(status=SessionStatus.OPEN),
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=SessionStatus.values),
                name="orders_session_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"Session {self.public_id}"


class Order(RestaurantScopedModel):
    session = models.ForeignKey(
        "orders.Session",
        on_delete=models.CASCADE,
        related_name="orders",
    )
    created_by = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_orders",
    )
    created_by_source = models.CharField(
        max_length=20,
        choices=CreatedBySource.choices,
        default=CreatedBySource.STAFF,
    )
    source = models.CharField(
        max_length=32,
        choices=OrderSource.choices,
        default=OrderSource.WAITER_MANUAL,
    )
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.DRAFT,
    )
    payment_status = models.CharField(
        max_length=20,
        choices=OrderPaymentStatus.choices,
        default=OrderPaymentStatus.UNPAID,
    )
    currency = models.CharField(max_length=3)
    total_amount = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    discount_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    tip_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    service_charge = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    notes = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(created_by_source__in=CreatedBySource.values),
                name="orders_order_created_by_source_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(source__in=OrderSource.values),
                name="orders_order_source_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=OrderStatus.values),
                name="orders_order_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(payment_status__in=OrderPaymentStatus.values),
                name="orders_order_payment_status_valid",
            ),
            models.UniqueConstraint(
                fields=["restaurant", "id"],
                name="orders_order_rest_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"Order {self.public_id}"


class Ticket(RestaurantScopedModel):
    session = models.ForeignKey(
        "orders.Session",
        on_delete=models.CASCADE,
        related_name="tickets",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="tickets",
    )
    status = models.CharField(
        max_length=20,
        choices=TicketStatus.choices,
        default=TicketStatus.INCOMING,
    )
    injected_at = models.DateTimeField()
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    # Human-friendly per-restaurant sequence that resets each day (rendered as
    # "T1", "T2", ... on the kitchen kanban instead of the opaque public_id).
    daily_number = models.PositiveIntegerField(null=True, blank=True)
    daily_seq_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["injected_at", "id"]
        indexes = [
            models.Index(
                fields=["restaurant", "status", "injected_at"],
                name="ord_tkt_rest_stat_inj_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=TicketStatus.values),
                name="orders_ticket_status_valid",
            ),
            models.UniqueConstraint(
                fields=["restaurant", "daily_seq_date", "daily_number"],
                name="orders_ticket_daily_number_uniq",
            ),
        ]

    @property
    def label(self) -> str:
        """Display label for the kitchen kanban, e.g. "T1" (empty until numbered)."""
        if self.daily_number is None:
            return ""
        return f"T{self.daily_number}"

    def _assign_daily_number(self) -> None:
        """Allocate the next per-restaurant, per-day sequence number."""
        injected = self.injected_at or timezone.now()
        seq_date = timezone.localdate(injected)
        self.daily_seq_date = seq_date
        with transaction.atomic():
            last = (
                Ticket.objects.select_for_update()
                .filter(restaurant_id=self.restaurant_id, daily_seq_date=seq_date)
                .aggregate(max_number=models.Max("daily_number"))["max_number"]
            )
            self.daily_number = (last or 0) + 1

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self._state.adding and self.daily_number is None:
            self._assign_daily_number()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Ticket {self.public_id}"


class OrderItem(RestaurantScopedModel):
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="items",
    )
    ticket = models.ForeignKey(
        "orders.Ticket",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items",
    )
    menu_item = models.ForeignKey(
        "menu.MenuItem",
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    guest_slot = models.PositiveIntegerField()
    quantity = models.PositiveIntegerField()
    comment = models.TextField(null=True, blank=True)
    modifiers = models.JSONField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=OrderItemStatus.choices,
        default=OrderItemStatus.PENDING,
    )
    unit_price = models.DecimalField(max_digits=14, decimal_places=4)
    total_price = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    # The order-level service charge, distributed across its items so the bill
    # reconciles: sum(item.payable) == Order.total_amount.
    service_charge_amount = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="voided_order_items",
    )
    void_reason = models.ForeignKey(
        "orders.VoidReason",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_items",
    )
    void_reason_note = models.TextField(null=True, blank=True)
    is_wasted = models.BooleanField(default=False)
    is_paid = models.BooleanField(default=False)

    class Meta:
        ordering = ["order_id", "guest_slot", "id"]
        indexes = [
            models.Index(
                fields=["restaurant", "status", "menu_item"],
                name="ord_item_rest_stat_menu_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=OrderItemStatus.values),
                name="orders_orderitem_status_valid",
            ),
        ]

    @property
    def payable(self) -> Decimal:
        """Full amount owed for this line: goods + its tax + its service share."""
        return self.total_price + self.tax_amount + self.service_charge_amount

    def __str__(self) -> str:
        return f"Order item {self.public_id}"
