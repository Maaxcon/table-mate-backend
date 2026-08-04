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
from apps.orders.models import OrderItemStatus, OrderPaymentStatus, OrderStatus
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
    order.payment_status = OrderPaymentStatus.PAID
    order.save(update_fields=["payment_status"])
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
    order.payment_status = OrderPaymentStatus.PAID
    order.save(update_fields=["status", "payment_status"])
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
def test_feedback_rejected_for_unpaid_order(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    """Feedback must not be accepted before the order is paid."""
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

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "paid" in response.data["detail"]
    assert not Feedback.objects.filter(order=order).exists()


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
    order.payment_status = OrderPaymentStatus.PAID
    order.save(update_fields=["status", "payment_status"])
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


@pytest.mark.django_db
def test_admin_feedback_list_rejects_malformed_filters(
    api: Any,
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    """Malformed admin filters must return 400, never 500."""
    admin = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
    list_url = reverse("admin-feedback-list")

    bad_params = [
        {"overall_rating": "abc"},
        {"service_rating": "abc"},
        {"overall_rating": "9"},
        {"date_from": "not-a-date"},
        {"date_to": "2023-13-40"},
        {"dish_id": "not-a-uuid"},
        {"ordering": "nonexistent_field_xyz"},
        {"ordering": "guest__email"},
        {"review_status": "archived"},
    ]
    for params in bad_params:
        response = admin.client.get(list_url, params)
        assert response.status_code == status.HTTP_400_BAD_REQUEST, (params, response.status_code)


@pytest.mark.django_db
def test_admin_feedback_list_accepts_valid_filters(
    api: Any,
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    """Valid admin filters are accepted and do not error."""
    admin = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
    list_url = reverse("admin-feedback-list")

    valid_params = [
        {"overall_rating": "5"},
        {"date_from": "2023-01-01"},
        {"date_from": "2023-01-01T00:00:00"},
        {"dish_id": str(item.public_id)},
        {"ordering": "-created_at"},
        {"ordering": "-overall_rating,-id"},
        {"ordering": "created_at,review_status"},
        {"review_status": "new"},
    ]
    for params in valid_params:
        response = admin.client.get(list_url, params)
        assert response.status_code == status.HTTP_200_OK, (params, response.status_code)


@pytest.mark.django_db
def test_update_without_dish_feedback_keeps_dish_ratings(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    """Omitting dish_feedback on update must keep existing dish ratings."""
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
    order.payment_status = OrderPaymentStatus.PAID
    order.save(update_fields=["payment_status"])
    order.items.update(status=OrderItemStatus.SERVED)

    client = _feedback_client(guest_id)
    create_response = client.post(
        reverse("guest-feedback-create"),
        {
            "order": str(order.public_id),
            "overall_rating": 5,
            "service_rating": 4,
            "dish_feedback": [{"menu_item": str(item.public_id), "rating": 5}],
        },
        format="json",
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    feedback = Feedback.objects.get(order=order)
    assert feedback.dish_feedback.count() == 1

    update_response = client.put(
        reverse("guest-feedback-detail", kwargs={"pk": feedback.public_id}),
        {
            "order": str(order.public_id),
            "overall_rating": 3,
            "service_rating": 3,
        },
        format="json",
    )
    assert update_response.status_code == status.HTTP_200_OK
    feedback.refresh_from_db()
    assert feedback.overall_rating == 3
    assert list(feedback.dish_feedback.values_list("menu_item_id", "rating")) == [(item.id, 5)]


@pytest.mark.django_db
def test_each_table_guest_can_submit_feedback_for_shared_checkout(
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
    second_item = MenuItem.objects.create(
        restaurant=restaurant,
        menu=item.menu,
        name="Second guest dish",
        price="12.00",
    )
    cart = ensure_active_cart_for_table(table=table)
    add_item_to_cart(session=cart, menu_item_id=str(item.public_id), quantity=1, guest_identity="guest-a")
    add_item_to_cart(
        session=cart,
        menu_item_id=str(second_item.public_id),
        quantity=1,
        guest_identity="guest-b",
    )

    with mock.patch("apps.orders.billing.is_restaurant_open", return_value=True):
        order = checkout_cart_session(cart_session=cart, user=None)
    order.payment_status = OrderPaymentStatus.PAID
    order.save(update_fields=["payment_status"])
    order.items.update(status=OrderItemStatus.SERVED)

    for guest_id, menu_item in (("guest-a", item), ("guest-b", second_item)):
        response = _feedback_client(guest_id).post(
            reverse("guest-feedback-create"),
            {
                "order": str(order.public_id),
                "overall_rating": 5,
                "service_rating": 4,
                "dish_feedback": [{"menu_item": str(menu_item.public_id), "rating": 5}],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    assert Feedback.objects.filter(order=order).count() == 2
    assert set(Feedback.objects.filter(order=order).values_list("guest_identity", flat=True)) == {
        "guest-a",
        "guest-b",
    }

    duplicate_response = _feedback_client("guest-a").post(
        reverse("guest-feedback-create"),
        {
            "order": str(order.public_id),
            "overall_rating": 5,
            "service_rating": 4,
        },
        format="json",
    )

    assert duplicate_response.status_code == status.HTTP_400_BAD_REQUEST
    assert duplicate_response.data["detail"] == "Feedback already exists for this order."


@pytest.mark.django_db
def test_update_with_empty_dish_feedback_clears_dish_ratings(
    restaurant: Restaurant,
    table: Table,
    item: Any,
    restaurant_settings: Any,
) -> None:
    """An explicit empty dish_feedback list on update clears dish ratings."""
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
    order.payment_status = OrderPaymentStatus.PAID
    order.save(update_fields=["payment_status"])
    order.items.update(status=OrderItemStatus.SERVED)

    client = _feedback_client(guest_id)
    create_response = client.post(
        reverse("guest-feedback-create"),
        {
            "order": str(order.public_id),
            "overall_rating": 5,
            "service_rating": 4,
            "dish_feedback": [{"menu_item": str(item.public_id), "rating": 5}],
        },
        format="json",
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    feedback = Feedback.objects.get(order=order)
    assert feedback.dish_feedback.count() == 1

    update_response = client.put(
        reverse("guest-feedback-detail", kwargs={"pk": feedback.public_id}),
        {
            "order": str(order.public_id),
            "overall_rating": 3,
            "service_rating": 3,
            "dish_feedback": [],
        },
        format="json",
    )
    assert update_response.status_code == status.HTTP_200_OK
    feedback.refresh_from_db()
    assert feedback.dish_feedback.count() == 0
