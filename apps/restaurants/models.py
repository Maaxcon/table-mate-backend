from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from common.models import BaseModel, RestaurantScopedModel

_WEEKDAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


def _parse_hhmm(v: object, label: str) -> tuple[int, int]:
    if not isinstance(v, str) or len(v) != 5 or v[2] != ":" or not v[:2].isdigit() or not v[3:].isdigit():
        raise ValidationError(f"'{label}' must be HH:MM format, got {v!r}.")
    hh, mm = int(v[:2]), int(v[3:])
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValidationError(f"'{label}' time out of range: {v!r}.")
    return hh, mm


def validate_working_hours(value: object) -> None:
    if not isinstance(value, dict):
        raise ValidationError("Must be an object.")
    for day, hours in value.items():
        if day not in _WEEKDAYS:
            raise ValidationError(f"Unknown day key: '{day}'. Use mon/tue/wed/thu/fri/sat/sun.")
        if not isinstance(hours, dict) or set(hours) != {"open", "close"}:
            raise ValidationError(f"'{day}' must have exactly 'open' and 'close' keys.")
        open_hhmm = _parse_hhmm(hours["open"], f"{day}.open")
        close_hhmm = _parse_hhmm(hours["close"], f"{day}.close")
        if open_hhmm == close_hhmm:
            raise ValidationError(f"'{day}.open' and '{day}.close' cannot be equal.")


class TableStatus(models.TextChoices):
    FREE = "free", "Free"
    OCCUPIED = "occupied", "Occupied"


class Restaurant(BaseModel):
    name = models.CharField(max_length=255)
    address = models.TextField()
    phone = models.CharField(max_length=32, blank=True, default="")
    cover_image = models.ImageField(upload_to="restaurants/covers/", null=True, blank=True)

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
    working_hours = models.JSONField(default=dict, validators=[validate_working_hours])
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
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
