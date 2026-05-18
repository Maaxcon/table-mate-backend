from django.db import models

from common.models import RestaurantScopedModel


class Layout(RestaurantScopedModel):
    version = models.PositiveIntegerField()
    payload = models.JSONField(default=dict)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_layouts",
    )

    class Meta:
        ordering = ["restaurant_id", "-version", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["restaurant", "version"],
                name="editor_layout_restaurant_version_unique",
            )
        ]

    def __str__(self) -> str:
        return f"Layout v{self.version} for {self.restaurant.name}"
