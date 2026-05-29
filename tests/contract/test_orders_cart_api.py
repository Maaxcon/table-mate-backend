# mypy: disable-error-code="no-untyped-call"
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from django.test import Client
from django.urls import reverse
from rest_framework import status

from apps.authentication.models import RoleCode, User
from apps.menu.models import MenuItem
from apps.orders.models import CartItem, CartSession, CartSessionStatus
from apps.reservations.models import Reservation, ReservationParticipant
from apps.restaurants.models import Restaurant, Table

from ..conftest import AuthContext, MenuItemFactory


def add_reservation_participant(reservation: Reservation, user: User) -> None:
    ReservationParticipant.objects.get_or_create(
        reservation=reservation,
        restaurant=reservation.restaurant,
        user=user,
    )


@pytest.fixture
def reservation(restaurant: Restaurant, table: Table) -> Reservation:
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        customer=None,
        guest_count=2,
        start_at=datetime.now(UTC) + timedelta(hours=1),
        end_at=datetime.now(UTC) + timedelta(hours=2),
    )


@pytest.fixture
def cart_item(menu: Any, category: Any) -> MenuItem:
    return cast(
        MenuItem,
        MenuItemFactory(
            restaurant=menu.restaurant,
            menu=menu,
            category=category,
            name="Burger",
            price=14.99,
            sort_order=1,
        ),
    )


@pytest.mark.django_db(databases=["default"])
class TestCartSessionCreate:
    url = reverse("cart-session-list")

    def test_unauthenticated_returns_401(self, api_client: Client) -> None:
        response = api_client.post(self.url, {"reservation": str(uuid.uuid4())}, content_type="application/json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_session(
        self, api: Callable[..., AuthContext], reservation: Reservation, restaurant: Restaurant
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        add_reservation_participant(reservation, auth.user)
        response = auth.client.post(
            self.url,
            {"reservation": str(reservation.public_id)},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["status"] == "active"
        assert data["reservation"] == str(reservation.public_id)
        assert data["participants"] == [str(auth.user.public_id)]

    def test_create_session_non_participant_returns_403(
        self,
        api: Callable[..., AuthContext],
        reservation: Reservation,
        restaurant: Restaurant,
    ) -> None:
        seeded = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        add_reservation_participant(reservation, seeded.user)

        intruder = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        response = intruder.client.post(
            self.url,
            {"reservation": str(reservation.public_id)},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_session_without_any_participants_returns_403(
        self,
        api: Callable[..., AuthContext],
        reservation: Reservation,
        restaurant: Restaurant,
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        # intentionally do not seed reservation participants
        response = auth.client.post(
            self.url,
            {"reservation": str(reservation.public_id)},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_session_invalid_reservation_returns_400(
        self, api: Callable[..., AuthContext], restaurant: Restaurant
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        response = auth.client.post(
            self.url,
            {"reservation": str(uuid.uuid4())},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db(databases=["default"])
class TestCartSessionList:
    url = reverse("cart-session-list")

    def test_list_own_sessions(
        self, api: Callable[..., AuthContext], reservation: Reservation, restaurant: Restaurant
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation, created_by=auth.user)
        session.participants.add(auth.user)

        response = auth.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["public_id"] == str(session.public_id)

    def test_list_excludes_non_participant_sessions(
        self, api: Callable[..., AuthContext], reservation: Reservation, restaurant: Restaurant
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        other = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
        other.participants.add(auth.user)

        auth2 = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        response = auth2.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 0


@pytest.mark.django_db(databases=["default"])
class TestCartSessionRetrieve:
    def test_retrieve_as_participant(
        self, api: Callable[..., AuthContext], reservation: Reservation, restaurant: Restaurant
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation, created_by=auth.user)
        session.participants.add(auth.user)

        url = reverse("cart-session-detail", kwargs={"pk": session.public_id})
        response = auth.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["public_id"] == str(session.public_id)

    def test_retrieve_non_participant_returns_404(
        self, api: Callable[..., AuthContext], reservation: Reservation, restaurant: Restaurant
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
        session.participants.add(auth.user)

        other = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        url = reverse("cart-session-detail", kwargs={"pk": session.public_id})
        response = other.client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db(databases=["default"])
class TestCartSessionPatchNotAllowed:
    def test_patch_returns_405(
        self, api: Callable[..., AuthContext], reservation: Reservation, restaurant: Restaurant
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation, created_by=auth.user)
        session.participants.add(auth.user)

        url = reverse("cart-session-detail", kwargs={"pk": session.public_id})
        response = auth.client.patch(
            url,
            {"reservation": str(reservation.public_id)},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db(databases=["default"])
class TestCartItemCreate:
    def test_add_item_as_participant(
        self,
        api: Callable[..., AuthContext],
        reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation, created_by=auth.user)
        session.participants.add(auth.user)

        url = reverse("cart-item-list", kwargs={"session_pk": session.public_id})
        response = auth.client.post(
            url,
            {"menu_item": str(cart_item.public_id), "quantity": 2},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["quantity"] == 2
        assert data["added_by"] == str(auth.user.public_id)

    def test_add_item_as_non_participant_returns_403(
        self,
        api: Callable[..., AuthContext],
        reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation, created_by=auth.user)
        session.participants.add(auth.user)

        intruder = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        url = reverse("cart-item-list", kwargs={"session_pk": session.public_id})
        response = intruder.client.post(
            url,
            {"menu_item": str(cart_item.public_id), "quantity": 1},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_add_item_closed_session_returns_409(
        self,
        api: Callable[..., AuthContext],
        reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        session = CartSession.objects.create(
            restaurant=restaurant,
            reservation=reservation,
            created_by=auth.user,
            status=CartSessionStatus.CLOSED,
        )
        session.participants.add(auth.user)

        url = reverse("cart-item-list", kwargs={"session_pk": session.public_id})
        response = auth.client.post(
            url,
            {"menu_item": str(cart_item.public_id), "quantity": 1},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert data["code"] == "cart_session_closed"

    def test_add_item_unauthenticated_returns_401(
        self,
        api_client: Client,
        reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
        url = reverse("cart-item-list", kwargs={"session_pk": session.public_id})
        response = api_client.post(
            url,
            {"menu_item": str(cart_item.public_id), "quantity": 1},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db(databases=["default"])
class TestCartItemList:
    def test_list_items_as_participant(
        self,
        api: Callable[..., AuthContext],
        reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation, created_by=auth.user)
        session.participants.add(auth.user)
        CartItem.objects.create(
            cart_session=session,
            menu_item=cart_item,
            quantity=2,
            added_by=auth.user,
            restaurant=restaurant,
        )

        url = reverse("cart-item-list", kwargs={"session_pk": session.public_id})
        response = auth.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["quantity"] == 2

    def test_list_items_non_participant_returns_empty(
        self,
        api: Callable[..., AuthContext],
        reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation, created_by=auth.user)
        session.participants.add(auth.user)
        CartItem.objects.create(
            cart_session=session,
            menu_item=cart_item,
            quantity=2,
            added_by=auth.user,
            restaurant=restaurant,
        )

        intruder = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        url = reverse("cart-item-list", kwargs={"session_pk": session.public_id})
        response = intruder.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 0


@pytest.mark.django_db(databases=["default"])
class TestCartItemDelete:
    def test_delete_item_as_participant(
        self,
        api: Callable[..., AuthContext],
        reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation, created_by=auth.user)
        session.participants.add(auth.user)
        item = CartItem.objects.create(
            cart_session=session,
            menu_item=cart_item,
            quantity=1,
            added_by=auth.user,
            restaurant=restaurant,
        )

        url = reverse("cart-item-detail", kwargs={"session_pk": session.public_id, "pk": item.public_id})
        response = auth.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert CartItem.objects.count() == 0

    def test_delete_item_as_non_participant_returns_403(
        self,
        api: Callable[..., AuthContext],
        reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation, created_by=auth.user)
        session.participants.add(auth.user)
        item = CartItem.objects.create(
            cart_session=session,
            menu_item=cart_item,
            quantity=1,
            added_by=auth.user,
            restaurant=restaurant,
        )

        intruder = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        url = reverse("cart-item-detail", kwargs={"session_pk": session.public_id, "pk": item.public_id})
        response = intruder.client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_item_closed_session_returns_409(
        self,
        api: Callable[..., AuthContext],
        reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        session = CartSession.objects.create(
            restaurant=restaurant,
            reservation=reservation,
            created_by=auth.user,
            status=CartSessionStatus.CLOSED,
        )
        session.participants.add(auth.user)
        item = CartItem.objects.create(
            cart_session=session,
            menu_item=cart_item,
            quantity=1,
            added_by=auth.user,
            restaurant=restaurant,
        )

        url = reverse("cart-item-detail", kwargs={"session_pk": session.public_id, "pk": item.public_id})
        response = auth.client.delete(url)
        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert data["code"] == "cart_session_closed"


@pytest.mark.django_db(databases=["default"])
class TestCartTwoUserScenario:
    """Two seeded users on the same reservation can add/remove items; a third user is rejected."""

    def test_two_users_can_add_and_remove(
        self,
        api: Callable[..., AuthContext],
        reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        user1 = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        user2 = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)

        add_reservation_participant(reservation, user1.user)
        add_reservation_participant(reservation, user2.user)

        session_resp = user1.client.post(
            reverse("cart-session-list"),
            {"reservation": str(reservation.public_id)},
            content_type="application/json",
        )
        assert session_resp.status_code == status.HTTP_201_CREATED
        session_id = session_resp.json()["public_id"]

        url = reverse("cart-item-list", kwargs={"session_pk": session_id})

        resp1 = user1.client.post(
            url,
            {"menu_item": str(cart_item.public_id), "quantity": 2},
            content_type="application/json",
        )
        assert resp1.status_code == status.HTTP_201_CREATED
        item_id = resp1.json()["public_id"]

        resp2 = user2.client.get(url)
        assert resp2.status_code == status.HTTP_200_OK
        assert resp2.json()["count"] == 1

        delete_url = reverse("cart-item-detail", kwargs={"session_pk": session_id, "pk": item_id})
        resp3 = user2.client.delete(delete_url)
        assert resp3.status_code == status.HTTP_204_NO_CONTENT

    def test_third_user_rejected(
        self,
        api: Callable[..., AuthContext],
        reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        user1 = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        user2 = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        intruder = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)

        add_reservation_participant(reservation, user1.user)
        add_reservation_participant(reservation, user2.user)

        session_resp = user1.client.post(
            reverse("cart-session-list"),
            {"reservation": str(reservation.public_id)},
            content_type="application/json",
        )
        assert session_resp.status_code == status.HTTP_201_CREATED
        session_id = session_resp.json()["public_id"]

        url = reverse("cart-item-list", kwargs={"session_pk": session_id})
        response = intruder.client.post(
            url,
            {"menu_item": str(cart_item.public_id), "quantity": 1},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        owner_add = user1.client.post(
            url,
            {"menu_item": str(cart_item.public_id), "quantity": 1},
            content_type="application/json",
        )
        assert owner_add.status_code == status.HTTP_201_CREATED
        item_id = owner_add.json()["public_id"]

        delete_url = reverse("cart-item-detail", kwargs={"session_pk": session_id, "pk": item_id})
        response = intruder.client.delete(delete_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN
