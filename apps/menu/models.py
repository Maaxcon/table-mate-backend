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
    ingredients = models.JSONField(default=list, blank=True)
    allergens = models.JSONField(default=list, blank=True)
    weight_grams = models.PositiveIntegerField(null=True, blank=True)
    image = models.ImageField(upload_to="menu_items/", null=True, blank=True)
    price = models.DecimalField(max_digits=14, decimal_places=4)
    is_available = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["menu_id", "sort_order", "id"]
        indexes = [
            models.Index(
                fields=["restaurant", "is_available"],
                name="menu_item_rest_avail_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["menu", "name"],
                name="menu_item_menu_name_unique",
            ),
            models.UniqueConstraint(
                fields=["restaurant", "id"],
                name="menu_menuitem_rest_uniq",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class MenuItemLike(RestaurantScopedModel):
    menu_item = models.ForeignKey(
        "menu.MenuItem",
        on_delete=models.CASCADE,
        related_name="likes",
    )
    guest_token = models.CharField(max_length=64)

    class Meta:
        ordering = ["menu_item_id", "id"]
        indexes = [
            models.Index(
                fields=["restaurant", "menu_item"],
                name="menu_item_like_rest_item_idx",
            ),
            models.Index(
                fields=["guest_token"],
                name="menu_item_like_guest_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["menu_item", "guest_token"],
                name="menu_item_like_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.menu_item_id}:{self.guest_token}"
