from datetime import timedelta
from typing import Any
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.feedback.models import Feedback
from apps.orders.billing import checkout_cart_session
from apps.orders.models import OrderItemStatus, OrderStatus
from apps.orders.services import add_item_to_cart, ensure_active_cart_for_table
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Restaurant, Table


def _feedback_client(guest_id: str) -> APIClient:
    token = AccessToken()
    token.payload["is_guest"] = True
    token.payload["guest_id"] = guest_id
    token.payload["feedback_only"] = True
    token.set_exp(lifetime=timedelta(days=7))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.mark.django_db
def test_table_guest_can_submit_feedback_for_own_order(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    now = timezone.now()
    Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=now - timedelta(minutes=30),
        end_at=now + timedelta(hours=1),
        status=ReservationStatus.ACTIVE,
        type=ReservationType.PRE_BOOKED,
    )
    cart = ensure_active_cart_for_table(table=table)
    guest_id = "guest-1"
    add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=1, guest_identity=guest_id)

    with mock.patch("apps.orders.billing.is_restaurant_open", return_value=True):
        order = checkout_cart_session(cart_session=cart, user=None)
    order.status = OrderStatus.COMPLETED
    order.save(update_fields=["status"])
    order.items.update(status=OrderItemStatus.SERVED)

    response = _feedback_client(guest_id).post(
        reverse("guest-feedback-create"),
        {
            "order": str(order.public_id),
            "overall_rating": 5,
            "service_rating": 4,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    feedback = Feedback.objects.get(order=order)
    assert feedback.guest_id is None
    assert feedback.guest_identity == guest_id
