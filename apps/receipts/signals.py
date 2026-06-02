import logging
from typing import Any

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.orders.models import Order, OrderStatus

from .services import create_receipt_from_order

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Order, dispatch_uid="receipts_create_on_order_completion")
def create_receipt_on_completion(sender: type[Order], instance: Order, **kwargs: Any) -> None:
    """When an order is completed, generate the customer's receipt snapshot."""
    if instance.status != OrderStatus.COMPLETED:
        return
    try:
        create_receipt_from_order(instance)
    except Exception:  # never let receipt creation break the order save
        logger.exception("Failed to create receipt for order %s", instance.pk)
