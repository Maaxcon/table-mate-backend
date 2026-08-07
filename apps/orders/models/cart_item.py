from django.db import models

from common.models import RestaurantScopedModel


class CartItem(RestaurantScopedModel):
    cart_session = models.ForeignKey(
        "orders.CartSession",
        on_delete=models.CASCADE,
        related_name="items",
    )
    menu_item = models.ForeignKey(
        "menu.MenuItem",
        on_delete=models.PROTECT,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField()
    added_by = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="added_cart_items",
    )
    comment = models.TextField(null=True, blank=True)

    guest_slot = models.PositiveIntegerField(null=True, blank=True)
    guest_identity = models.CharField(max_length=255, null=True, blank=True)

    # Applied modifier choices, denormalized for display/price (snapshot):
    # [{"modifier_id", "option_id", "name", "price_delta"}]. modifiers_key is a
    # deterministic fingerprint of the canonical set so cart lines can be
    # keyed by (session, item, modifier-set).
    modifiers = models.JSONField(default=list, blank=True)
    modifiers_key = models.CharField(max_length=64, null=True, blank=True)
    # Unit price snapshot including modifier price deltas (base + sum of deltas).
    unit_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="orders_cartitem_quantity_gte_1",
            ),
            models.UniqueConstraint(
                fields=["cart_session", "menu_item"],
                condition=models.Q(modifiers_key__isnull=True),
                name="orders_cartitem_unique_session_item_nomod",
            ),
            models.UniqueConstraint(
                fields=["cart_session", "menu_item", "modifiers_key"],
                condition=models.Q(modifiers_key__isnull=False),
                name="orders_cartitem_unique_session_item_mod",
            ),
            models.UniqueConstraint(
                fields=["restaurant", "id"],
                name="orders_cartitem_rest_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"CartItem {self.public_id}"
