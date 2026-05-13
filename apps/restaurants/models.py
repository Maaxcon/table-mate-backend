from django.db import models

from common.models import BaseModel


class Restaurant(BaseModel):
    name = models.CharField(max_length=255)
    address = models.TextField()

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name


class RestaurantSettings(BaseModel):
    restaurant = models.OneToOneField(
        "restaurants.Restaurant",
        on_delete=models.CASCADE,
        related_name="settings",
    )
    timezone = models.CharField(max_length=64, default="UTC")
    currency = models.CharField(max_length=3)
    locale = models.CharField(max_length=16, default="en")
    default_tax_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    default_service_charge = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    working_hours = models.JSONField(default=dict)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"Settings for {self.restaurant.name}"
