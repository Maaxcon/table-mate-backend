from datetime import timedelta
from typing import Any
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.authentication.models import RoleCode
from apps.feedback.models import Feedback
from apps.menu.models import Menu, MenuItem
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
    api: Any,
    restaurant: Restaurant,
    empty_restaurant: Restaurant,
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
            "dish_feedback": [{"menu_item": str(item.public_id), "rating": 5}],
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    feedback = Feedback.objects.get(order=order)
    assert feedback.guest_id is None
    assert feedback.guest_identity == guest_id

    admin = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
    detail_response = admin.client.get(
        reverse("admin-feedback-detail", kwargs={"public_id": feedback.public_id}),
    )

    assert detail_response.status_code == status.HTTP_200_OK
    assert detail_response.data["review_status"] == "reviewed"
    feedback.refresh_from_db()
    assert feedback.review_status == "reviewed"

    list_response = admin.client.get(f"{reverse('admin-feedback-list')}?restaurant_id=999999")

    assert list_response.status_code == status.HTTP_200_OK
    assert [entry["public_id"] for entry in list_response.data["results"]] == [str(feedback.public_id)]

    foreign_menu = Menu.objects.create(restaurant=empty_restaurant, name="Foreign menu")
    foreign_item = MenuItem.objects.create(
        restaurant=empty_restaurant,
        menu=foreign_menu,
        name="Foreign dish",
        price="12.00",
    )
    invalid_update = _feedback_client(guest_id).put(
        reverse("guest-feedback-detail", kwargs={"pk": feedback.public_id}),
        {
            "order": str(order.public_id),
            "overall_rating": 1,
            "service_rating": 1,
            "dish_feedback": [{"menu_item": str(foreign_item.public_id), "rating": 1}],
        },
        format="json",
    )

    assert invalid_update.status_code == status.HTTP_400_BAD_REQUEST
    feedback.refresh_from_db()
    assert feedback.overall_rating == 5
    assert feedback.service_rating == 4
    assert list(feedback.dish_feedback.values_list("menu_item_id", "rating")) == [(item.id, 5)]

    duplicate_update = _feedback_client(guest_id).put(
        reverse("guest-feedback-detail", kwargs={"pk": feedback.public_id}),
        {
            "order": str(order.public_id),
            "overall_rating": 1,
            "service_rating": 1,
            "dish_feedback": [
                {"menu_item": str(item.public_id), "rating": 1},
                {"menu_item": str(item.public_id), "rating": 1},
            ],
        },
        format="json",
    )

    assert duplicate_update.status_code == status.HTTP_400_BAD_REQUEST
    feedback.refresh_from_db()
    assert feedback.overall_rating == 5
    assert feedback.service_rating == 4
    assert list(feedback.dish_feedback.values_list("menu_item_id", "rating")) == [(item.id, 5)]


@pytest.mark.django_db
def test_receipt_owner_can_submit_feedback_for_qr_order(
    api: Any,
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    customer = api()
    now = timezone.now()
    Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        customer=customer.user,
        guest_count=2,
        start_at=now - timedelta(minutes=30),
        end_at=now + timedelta(hours=1),
        status=ReservationStatus.ACTIVE,
        type=ReservationType.PRE_BOOKED,
    )
    cart = ensure_active_cart_for_table(table=table)
    add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=1, guest_identity="guest-1")

    with mock.patch("apps.orders.billing.is_restaurant_open", return_value=True):
        order = checkout_cart_session(cart_session=cart, user=None)
    order.status = OrderStatus.COMPLETED
    order.save(update_fields=["status"])
    order.items.update(status=OrderItemStatus.SERVED)

    response = customer.client.post(
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
    assert feedback.guest_id == customer.user.id
    assert feedback.guest_identity is None


@pytest.mark.django_db
def test_deleting_user_with_feedback_anonymizes_instead_of_breaking_constraint(
    api: Any,
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    """User erasure must not abort on feedback_single_owner; ratings survive detached."""
    customer = api()
    now = timezone.now()
    Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        customer=customer.user,
        guest_count=2,
        start_at=now - timedelta(minutes=30),
        end_at=now + timedelta(hours=1),
        status=ReservationStatus.ACTIVE,
        type=ReservationType.PRE_BOOKED,
    )
    cart = ensure_active_cart_for_table(table=table)
    add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=1, guest_identity="guest-1")

    with mock.patch("apps.orders.billing.is_restaurant_open", return_value=True):
        order = checkout_cart_session(cart_session=cart, user=None)
    order.status = OrderStatus.COMPLETED
    order.save(update_fields=["status"])
    order.items.update(status=OrderItemStatus.SERVED)

    response = customer.client.post(
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
    assert feedback.guest_id == customer.user.id

    customer.user.delete()

    feedback.refresh_from_db()
    assert feedback.guest_id is None
    assert feedback.guest_identity is not None
    assert feedback.overall_rating == 5
