from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.authentication.models import User
from apps.menu.models import MenuItem
from apps.orders.models import Order, OrderItemStatus, OrderStatus
from common.exceptions import DomainError

from .models import DishFeedback, Feedback, FeedbackReviewStatus


def _validate_order_for_feedback(
    *,
    order: Order,
    guest: User | None,
    guest_identity: str | None,
) -> None:
    if order.status != OrderStatus.COMPLETED:
        raise DomainError("Feedback can only be submitted for completed orders.")
    if order.created_by_id is not None and order.created_by_id != getattr(guest, "id", None):
        raise DomainError("You can only submit feedback for your own orders.")
    if order.created_by_id is None and (
        not guest_identity or not order.items.filter(guest_identity=guest_identity).exists()
    ):
        raise DomainError("You can only submit feedback for your own orders.")
    if order.restaurant_id is None:
        raise DomainError("Order has no associated restaurant.")
    served_items = order.items.exclude(
        status__in=[OrderItemStatus.SERVED, OrderItemStatus.VOIDED],
    )
    if served_items.exists():
        raise DomainError("All order items must be served or voided before submitting feedback.")
    if hasattr(order, "feedback"):
        raise DomainError("Feedback already exists for this order.")


@transaction.atomic
def create_feedback(
    *,
    guest: User | None,
    guest_identity: str | None = None,
    order_id: UUID,
    overall_rating: int,
    service_rating: int,
    comment: str = "",
    dish_feedback_data: list[dict[str, Any]] | None = None,
) -> Feedback:
    from apps.orders.selectors import get_order_by_public_id

    order = get_order_by_public_id(order_id=str(order_id))
    if order is None:
        raise DomainError("Order not found.")

    _validate_order_for_feedback(order=order, guest=guest, guest_identity=guest_identity)

    feedback = Feedback.objects.create(
        restaurant_id=order.restaurant_id,
        guest=guest,
        guest_identity=guest_identity,
        order=order,
        overall_rating=overall_rating,
        service_rating=service_rating,
        comment=comment,
    )

    if dish_feedback_data:
        for item_data in dish_feedback_data:
            menu_item_public_id = item_data["menu_item"]
            try:
                menu_item = MenuItem.objects.get(public_id=menu_item_public_id)
            except MenuItem.DoesNotExist:
                raise DomainError(f"Menu item {menu_item_public_id} not found.") from None

            order_item_ids = order.items.filter(
                menu_item=menu_item,
            ).values_list("id", flat=True)
            if not order_item_ids.exists():
                raise DomainError(f"Menu item {menu_item_public_id} is not part of this order.")

            DishFeedback.objects.create(
                feedback=feedback,
                menu_item=menu_item,
                rating=item_data["rating"],
                comment=item_data.get("comment", ""),
            )

    return feedback


@transaction.atomic
def update_feedback_review_status(
    *,
    feedback: Feedback,
    review_status: str,
) -> Feedback:
    if review_status not in FeedbackReviewStatus.values:
        raise DomainError(f"Invalid review_status. Choose from: {', '.join(FeedbackReviewStatus.values)}")
    feedback.review_status = review_status
    feedback.save(update_fields=["review_status", "updated_at"])
    return feedback


def record_prompt_shown(*, feedback: Feedback) -> Feedback:
    feedback.prompt_shown_at = timezone.now()
    feedback.save(update_fields=["prompt_shown_at", "updated_at"])
    return feedback


def dismiss_feedback_prompt(*, feedback: Feedback) -> Feedback:
    feedback.dismissed = True
    feedback.prompt_shown_at = timezone.now()
    feedback.save(update_fields=["dismissed", "prompt_shown_at", "updated_at"])
    return feedback
