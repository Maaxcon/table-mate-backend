from django.contrib import admin

from .models import DishFeedback, Feedback


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = [
        "public_id",
        "guest",
        "restaurant",
        "order",
        "overall_rating",
        "service_rating",
        "review_status",
        "created_at",
    ]
    list_filter = ["review_status", "overall_rating", "service_rating", "restaurant", "created_at"]
    search_fields = ["guest__email", "comment"]
    readonly_fields = ["public_id", "created_at", "updated_at"]


@admin.register(DishFeedback)
class DishFeedbackAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["id", "feedback", "menu_item", "rating", "created_at"]
    list_filter = ["rating"]
    search_fields = ["menu_item__name", "comment"]
