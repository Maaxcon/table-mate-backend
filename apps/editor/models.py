import uuid

from django.db import models
from django.utils import timezone

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


class LayoutVersion(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, db_index=True, unique=True, editable=False)
    restaurant = models.ForeignKey("restaurants.Restaurant", on_delete=models.PROTECT, related_name="layout_versions")
    parent_version = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="child_versions",
    )
    layout_json = models.JSONField(default=dict)
    published_at = models.DateTimeField(default=timezone.now)
    published_by = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="layout_versions_published",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["restaurant_id", "-published_at", "-id"]

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise RuntimeError("LayoutVersion is immutable once created")
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"LayoutVersion {self.public_id} for restaurant {self.restaurant_id}"


class LayoutDraft(models.Model):
    restaurant = models.ForeignKey("restaurants.Restaurant", on_delete=models.CASCADE, related_name="layout_drafts")
    base_version = models.ForeignKey(
        LayoutVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts_based_on",
    )
    draft_json = models.JSONField(default=dict)
    owner = models.ForeignKey("authentication.User", on_delete=models.CASCADE)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["restaurant", "owner"], name="editor_layoutdraft_restaurant_owner_unique")
        ]

    def __str__(self) -> str:
        return f"LayoutDraft for restaurant {self.restaurant_id}, owner {self.owner_id}"
