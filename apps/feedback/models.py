from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from common.models import BaseModel, RestaurantScopedModel


class FeedbackReviewStatus(models.TextChoices):
    NEW = "new", "New"
    REVIEWED = "reviewed", "Reviewed"
    RESOLVED = "resolved", "Resolved"


class Feedback(RestaurantScopedModel):
    guest = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback",
    )
    guest_identity = models.CharField(max_length=255, null=True, blank=True)
    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="feedback",
    )
    overall_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    service_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comment = models.TextField(blank=True, default="")
    review_status = models.CharField(
        max_length=20,
        choices=FeedbackReviewStatus.choices,
        default=FeedbackReviewStatus.NEW,
    )
    prompt_shown_at = models.DateTimeField(null=True, blank=True)
    dismissed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(overall_rating__gte=1, overall_rating__lte=5),
                name="feedback_overall_rating_range",
            ),
            models.CheckConstraint(
                condition=models.Q(service_rating__gte=1, service_rating__lte=5),
                name="feedback_service_rating_range",
            ),
            models.CheckConstraint(
                condition=models.Q(review_status__in=FeedbackReviewStatus.values),
                name="feedback_review_status_valid",
            ),
            models.UniqueConstraint(
                fields=["restaurant", "id"],
                name="feedback_rest_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(guest__isnull=False, guest_identity__isnull=True)
                    | models.Q(guest__isnull=True, guest_identity__isnull=False)
                ),
                name="feedback_single_owner",
            ),
        ]

    def __str__(self) -> str:
        return f"Feedback {self.public_id} by {self.guest_id or self.guest_identity}"


class DishFeedback(BaseModel):
    feedback = models.ForeignKey(
        "feedback.Feedback",
        on_delete=models.CASCADE,
        related_name="dish_feedback",
    )
    menu_item = models.ForeignKey(
        "menu.MenuItem",
        on_delete=models.CASCADE,
        related_name="dish_feedback",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comment = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name="dishfeedback_rating_range",
            ),
            models.UniqueConstraint(
                fields=["feedback", "menu_item"],
                name="dishfeedback_feedback_menu_item_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"DishFeedback {self.id} for {self.menu_item_id}"
