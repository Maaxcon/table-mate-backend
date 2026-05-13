from django.db import models

from common.models import BaseModel, RestaurantScopedModel


class Menu(RestaurantScopedModel):
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name


class MenuCategory(BaseModel):
    menu = models.ForeignKey(
        "menu.Menu",
        on_delete=models.CASCADE,
        related_name="categories",
    )
    name = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["menu_id", "sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["menu", "name"],
                name="menu_category_menu_name_unique",
            )
        ]

    def __str__(self) -> str:
        return self.name


class MenuItem(RestaurantScopedModel):
    menu = models.ForeignKey(
        "menu.Menu",
        on_delete=models.CASCADE,
        related_name="items",
    )
    category = models.ForeignKey(
        "menu.MenuCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    price = models.DecimalField(max_digits=14, decimal_places=4)
    is_available = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["menu_id", "sort_order", "id"]
        indexes = [
            models.Index(fields=["restaurant", "is_available"], name="menu_item_restaurant_available_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["menu", "name"],
                name="menu_item_menu_name_unique",
            )
        ]

    def __str__(self) -> str:
        return self.name
