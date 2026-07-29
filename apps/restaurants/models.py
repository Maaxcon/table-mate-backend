from typing import Any

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


class Restaurant(BaseModel):
    name = models.CharField(max_length=255)
    address = models.TextField()
    phone = models.CharField(max_length=32, blank=True, default="")
    cover_image = models.ImageField(upload_to="restaurants/covers/", null=True, blank=True)
    telegram_url = models.URLField(max_length=255, blank=True, default="")
    facebook_url = models.URLField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name


class RestaurantTranslation(models.Model):
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        on_delete=models.CASCADE,
        related_name="translations",
    )
    language_code = models.CharField(max_length=10)
    address = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["restaurant_id", "language_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["restaurant", "language_code"],
                name="restaurant_translation_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.language_code}] {self.restaurant.name}"


class RestaurantSettings(BaseModel):
    restaurant = models.OneToOneField(
        "restaurants.Restaurant",
        on_delete=models.CASCADE,
        related_name="settings",
    )
    timezone = models.CharField(max_length=64, default="UTC")
    currency = models.CharField(max_length=3)
    locale = models.CharField(max_length=16, default="en")
    supported_languages = models.JSONField(default=list, blank=True)
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

    def clean(self) -> None:
        super().clean()
        if self.supported_languages:
            if self.locale not in self.supported_languages:
                raise ValidationError(
                    {"locale": f"'{self.locale}' must be in supported_languages: {self.supported_languages}"}
                )

    def save(self, *args: Any, **kwargs: Any) -> None:
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Settings for {self.restaurant.name}"


class Zone(BaseModel):
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        on_delete=models.CASCADE,
        related_name="zones",
    )
    name = models.CharField(max_length=128)
    sort_order = models.PositiveIntegerField(default=0)
    edge_styles = models.JSONField(default=dict, blank=True)
    canvas_cols = models.PositiveIntegerField(default=20)
    canvas_rows = models.PositiveIntegerField(default=20)

    class Meta:
        ordering = ["restaurant_id", "sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["restaurant", "name"],
                name="restaurants_zone_restaurant_name_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.restaurant.name} / {self.name}"


class Table(RestaurantScopedModel):
    public_number = models.CharField(max_length=64, db_index=True)
    capacity = models.PositiveIntegerField()
    active = models.BooleanField(default=True)
    zone = models.ForeignKey(
        Zone,
        on_delete=models.PROTECT,
        related_name="tables",
    )

    class Meta:
        ordering = ["restaurant_id", "public_number", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["restaurant", "public_number"],
                condition=models.Q(active=True),
                name="restaurants_table_restaurant_public_number_active_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.restaurant.name} / {self.public_number}"
