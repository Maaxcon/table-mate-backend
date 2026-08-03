from datetime import datetime
from typing import Any

from django.db.models import Avg, Count, DecimalField, QuerySet
from django.db.models.functions import Coalesce

from .models import DishFeedback, Feedback


def get_feedback_list(
    *,
    queryset: QuerySet[Feedback],
    review_status: str | None = None,
    overall_rating: int | None = None,
    service_rating: int | None = None,
    dish_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    ordering: list[str] | None = None,
) -> QuerySet[Feedback]:
    qs = queryset.select_related("restaurant", "guest", "order").prefetch_related("dish_feedback__menu_item")

    if review_status is not None:
        qs = qs.filter(review_status=review_status)
    if overall_rating is not None:
        qs = qs.filter(overall_rating=overall_rating)
    if service_rating is not None:
        qs = qs.filter(service_rating=service_rating)
    if date_from is not None:
        qs = qs.filter(created_at__gte=date_from)
    if date_to is not None:
        qs = qs.filter(created_at__lte=date_to)
    if dish_id is not None:
        qs = qs.filter(dish_feedback__menu_item__public_id=dish_id).distinct()

    if ordering:
        qs = qs.order_by(*ordering)
    else:
        qs = qs.order_by("-created_at", "-id")

    return qs


def get_guest_feedback_list(
    *,
    guest_id: int | None = None,
    guest_identity: str | None = None,
) -> QuerySet[Feedback]:
    filters = {"guest_id": guest_id} if guest_id is not None else {"guest_identity": guest_identity}
    return (
        Feedback.objects.filter(**filters)
        .select_related("restaurant")
        .prefetch_related("dish_feedback__menu_item")
        .order_by("-created_at", "-id")
    )


def get_guest_feedback(*, guest_id: int, feedback_pk: str) -> Feedback | None:
    return (
        Feedback.objects.filter(guest_id=guest_id, public_id=feedback_pk)
        .select_related("restaurant")
        .prefetch_related("dish_feedback__menu_item")
        .first()
    )


def get_dish_ratings(*, restaurant_id: int | None = None) -> QuerySet[Any]:
    qs = DishFeedback.objects.values("menu_item_id").annotate(
        average_rating=Coalesce(
            Avg("rating"),
            0,
            output_field=DecimalField(max_digits=3, decimal_places=2),
        ),
        rating_count=Count("id"),
    )
    if restaurant_id is not None:
        qs = qs.filter(feedback__restaurant_id=restaurant_id)
    return qs


def get_menu_item_rating(*, menu_item_id: int) -> dict[str, object]:
    agg = DishFeedback.objects.filter(menu_item_id=menu_item_id).aggregate(
        average_rating=Coalesce(
            Avg("rating"),
            0,
            output_field=DecimalField(max_digits=3, decimal_places=2),
        ),
        rating_count=Count("id"),
    )
    return {
        "average_rating": agg["average_rating"] or None,
        "rating_count": agg["rating_count"] or 0,
    }


def get_restaurant_rating(*, restaurant_id: int) -> dict[str, object]:
    agg = Feedback.objects.filter(restaurant_id=restaurant_id).aggregate(
        average_rating=Coalesce(
            Avg("overall_rating"),
            0,
            output_field=DecimalField(max_digits=3, decimal_places=2),
        ),
        rating_count=Count("id"),
    )
    return {
        "average_rating": agg["average_rating"] or None,
        "rating_count": agg["rating_count"] or 0,
    }
