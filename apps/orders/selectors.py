from django.db.models import Q, QuerySet

from .models import Order


def get_customer_orders(customer_id: int, restaurant_id: int) -> QuerySet[Order]:
    """Orders that belong to a customer's own history within one restaurant.

    A customer is linked to an order either directly (they created it, e.g. a
    prepaid order) or through the reservation behind the order's session.
    Ordered newest-first by the model's default ordering.
    """
    return (
        Order.objects.filter(restaurant_id=restaurant_id)
        .filter(Q(created_by_id=customer_id) | Q(session__reservation__customer_id=customer_id))
        .select_related("session", "created_by")
        .distinct()
    )
