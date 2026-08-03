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
    if guest is not None:
        owns_order = order.created_by_id == guest.id
        if not owns_order:
            from apps.receipts.models import Receipt

            owns_order = Receipt.objects.filter(order=order, customer=guest).exists()
        if not owns_order:
            raise DomainError("You can only submit feedback for your own orders.")
    elif not guest_identity or not order.items.filter(guest_identity=guest_identity).exists():
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


def _resolve_dish_feedback_data(
    *,
    order: Order,
    restaurant_id: int,
    dish_feedback_data: list[dict[str, Any]],
) -> list[tuple[MenuItem, dict[str, Any]]]:
    resolved: list[tuple[MenuItem, dict[str, Any]]] = []
    menu_item_ids: set[str] = set()

    for item_data in dish_feedback_data:
        menu_item_public_id = item_data["menu_item"]
        menu_item_key = str(menu_item_public_id)
        if menu_item_key in menu_item_ids:
            raise DomainError("Each dish can only be rated once.")
        menu_item_ids.add(menu_item_key)

        menu_item = MenuItem.objects.filter(
            public_id=menu_item_public_id,
            restaurant_id=restaurant_id,
        ).first()
        if menu_item is None:
            raise DomainError(f"Menu item {menu_item_public_id} not found.")
        if not order.items.filter(menu_item_id=menu_item.id).exists():
            raise DomainError(f"Menu item {menu_item_public_id} is not part of this order.")
        resolved.append((menu_item, item_data))

    return resolved


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
    resolved_dish_feedback = _resolve_dish_feedback_data(
        order=order,
        restaurant_id=order.restaurant_id,
        dish_feedback_data=dish_feedback_data or [],
    )

    feedback = Feedback.objects.create(
        restaurant_id=order.restaurant_id,
        guest=guest,
        guest_identity=guest_identity,
        order=order,
        overall_rating=overall_rating,
        service_rating=service_rating,
        comment=comment,
    )

    for menu_item, item_data in resolved_dish_feedback:
        DishFeedback.objects.create(
            feedback=feedback,
            menu_item=menu_item,
            rating=item_data["rating"],
            comment=item_data.get("comment", ""),
        )

    return feedback


@transaction.atomic
def update_feedback(
    *,
    feedback: Feedback,
    overall_rating: int,
    service_rating: int,
    comment: str,
    dish_feedback_data: list[dict[str, Any]] | None,
) -> Feedback:
    feedback.overall_rating = overall_rating
    feedback.service_rating = service_rating
    feedback.comment = comment
    feedback.save(update_fields=["overall_rating", "service_rating", "comment", "updated_at"])

    # Omitted dish_feedback means "keep the existing dish ratings"; only an
    # explicit list (including []) replaces them.
    if dish_feedback_data is not None:
        resolved_dish_feedback = _resolve_dish_feedback_data(
            order=feedback.order,
            restaurant_id=feedback.restaurant_id,
            dish_feedback_data=dish_feedback_data,
        )
        feedback.dish_feedback.all().delete()
        DishFeedback.objects.bulk_create(
            [
                DishFeedback(
                    feedback=feedback,
                    menu_item=menu_item,
                    rating=item_data["rating"],
                    comment=item_data.get("comment", ""),
                )
                for menu_item, item_data in resolved_dish_feedback
            ],
        )

    feedback.refresh_from_db()
    return feedback


@transaction.atomic
def mark_feedback_reviewed(*, feedback: Feedback) -> Feedback:
    if feedback.review_status == FeedbackReviewStatus.NEW:
        feedback.review_status = FeedbackReviewStatus.REVIEWED
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
