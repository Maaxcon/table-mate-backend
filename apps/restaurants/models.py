from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator

from common.models import BaseModel, RestaurantScopedModel


class TableStatus(models.TextChoices):
    FREE = "free", "Free"
    OCCUPIED = "occupied", "Occupied"


class Restaurant(BaseModel):
    name = models.CharField(max_length=255)
    address = models.TextField()
    phone = models.CharField(max_length=32, blank=True, default="")

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
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=4.8,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    eta_min_minutes = models.PositiveSmallIntegerField(default=20)
    eta_max_minutes = models.PositiveSmallIntegerField(default=30)
    price_band = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(4)],
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(eta_min_minutes__lte=models.F("eta_max_minutes")),
                name="restaurant_settings_eta_range_valid",
            )
        ]

    def __str__(self) -> str:
        return f"Settings for {self.restaurant.name}"


class TableShape(models.TextChoices):
    RECTANGLE = "rectangle", "Rectangle"
    ROUND = "round", "Round"
    SQUARE = "square", "Square"
    BOOTH = "booth", "Booth"


class Table(RestaurantScopedModel):
    table_number = models.CharField(max_length=64)
    capacity = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20,
        choices=TableStatus.choices,
        default=TableStatus.FREE,
    )
    shape = models.CharField(
        max_length=20,
        choices=TableShape.choices,
        default=TableShape.RECTANGLE,
    )
    active = models.BooleanField(default=True)
    position_x = models.IntegerField(null=True, blank=True)
    position_y = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["restaurant_id", "table_number", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["restaurant", "table_number"],
                name="restaurants_table_restaurant_number_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=TableStatus.values),
                name="restaurants_table_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.restaurant.name} / {self.table_number}"
