from django.db import models

from common.models import RestaurantScopedModel


class GuestProfile(RestaurantScopedModel):
    """Maps a guest device identity to a human-readable display name within a cart session."""

    cart_session = models.ForeignKey(
        "orders.CartSession",
        on_delete=models.CASCADE,
        related_name="guest_profiles",
    )
    guest_identity = models.CharField(max_length=255)
    display_name = models.CharField(max_length=128)

    class Meta:
        ordering = ["created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["cart_session", "guest_identity"],
                name="orders_guestprofile_identity_unique_per_session",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.guest_identity[:8]}…)"
