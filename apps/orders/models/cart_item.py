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

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="orders_cartitem_quantity_gte_1",
            ),
            models.UniqueConstraint(
                fields=["cart_session", "menu_item"],
                name="orders_cartitem_unique_session_item",
            ),
        ]

    def __str__(self) -> str:
        return f"CartItem {self.public_id}"
