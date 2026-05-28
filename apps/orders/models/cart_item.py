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

    def __str__(self) -> str:
        return f"CartItem {self.public_id}"
