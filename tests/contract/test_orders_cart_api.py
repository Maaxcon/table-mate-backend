# mypy: disable-error-code="no-untyped-call"
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from django.db import close_old_connections
from django.test import Client
from django.urls import reverse
from rest_framework import status

from apps.authentication.models import RoleCode, User
from apps.menu.models import MenuItem
from apps.orders.models import CartItem, CartSession, CartSessionStatus, Session, SessionStatus
from apps.reservations.models import Reservation
from apps.restaurants.models import Restaurant, Table, Zone

from ..conftest import AuthContext, MenuItemFactory


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
def second_reservation(restaurant: Restaurant, table: Table) -> Reservation:
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        customer=None,
        guest_count=2,
        start_at=datetime.now(UTC) + timedelta(hours=3),
        end_at=datetime.now(UTC) + timedelta(hours=4),
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


def _open_visit_session(reservation: Reservation, restaurant: Restaurant) -> None:
    Session.objects.create(
        restaurant=restaurant,
        table=reservation.table,
        reservation=reservation,
        guest_count=reservation.guest_count,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=reservation.start_at,
        ends_at=reservation.end_at,
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

    def test_create_session_without_reservation_membership_succeeds(
        self,
        api: Callable[..., AuthContext],
        reservation: Reservation,
        restaurant: Restaurant,
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        response = auth.client.post(
            self.url,
            {"reservation": str(reservation.public_id)},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["participants"] == [str(auth.user.public_id)]

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

    def test_re_add_with_comment_updates_stored_comment(
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

        auth.client.post(
            url,
            {"menu_item": str(cart_item.public_id), "quantity": 1},
            content_type="application/json",
        )
        # Same item again, now with a note: it must merge quantity AND store the note.
        response = auth.client.post(
            url,
            {"menu_item": str(cart_item.public_id), "quantity": 1, "comment": "no onions"},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        body = response.json()
        assert body["quantity"] == 2
        assert body["comment"] == "no onions"

        # A later add without a comment must not wipe the existing note.
        auth.client.post(
            url,
            {"menu_item": str(cart_item.public_id), "quantity": 1},
            content_type="application/json",
        )
        list_resp = auth.client.get(url)
        results = list_resp.json()["results"]
        line = next(i for i in results if i["menu_item"] == str(cart_item.public_id))
        assert line["comment"] == "no onions"

    def test_response_includes_menu_item_snapshot(
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
            {"menu_item": str(cart_item.public_id), "quantity": 1},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        snapshot = response.json()["menu_item_detail"]
        assert snapshot["id"] == str(cart_item.public_id)
        assert snapshot["name"] == cart_item.name
        assert "price" in snapshot

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
        reservation.customer = intruder.user
        reservation.save(update_fields=["customer"])
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

        session_resp = user1.client.post(
            reverse("cart-session-list"),
            {"reservation": str(reservation.public_id)},
            content_type="application/json",
        )
        assert session_resp.status_code == status.HTTP_201_CREATED
        session_id = session_resp.json()["public_id"]

        session_join = user2.client.post(
            reverse("cart-session-list"),
            {"reservation": str(reservation.public_id)},
            content_type="application/json",
        )
        assert session_join.status_code == status.HTTP_201_CREATED
        assert session_join.json()["public_id"] == session_id

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

        session_resp = user1.client.post(
            reverse("cart-session-list"),
            {"reservation": str(reservation.public_id)},
            content_type="application/json",
        )
        assert session_resp.status_code == status.HTTP_201_CREATED
        session_id = session_resp.json()["public_id"]

        session_join = user2.client.post(
            reverse("cart-session-list"),
            {"reservation": str(reservation.public_id)},
            content_type="application/json",
        )
        assert session_join.status_code == status.HTTP_201_CREATED

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


@pytest.mark.django_db(databases=["default"])
class TestCartItemPatch:
    def test_patch_quantity(
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
            quantity=2,
            added_by=auth.user,
            restaurant=restaurant,
        )

        url = reverse("cart-item-detail", kwargs={"session_pk": session.public_id, "pk": item.public_id})
        response = auth.client.patch(
            url,
            {"quantity": 5},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["quantity"] == 5

    def test_patch_with_guest_slot(
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
        response = auth.client.patch(
            url,
            {"quantity": 3, "guest_slot": 2},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["quantity"] == 3
        assert data["guest_slot"] == 2

    def test_patch_non_participant_returns_403(
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
        response = intruder.client.patch(
            url,
            {"quantity": 5},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_patch_closed_session_returns_409(
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
        response = auth.client.patch(
            url,
            {"quantity": 5},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert data["code"] == "cart_session_closed"


@pytest.mark.django_db(databases=["default"])
class TestCartItemUnavailable:
    def test_add_unavailable_item_returns_400(
        self,
        api: Callable[..., AuthContext],
        reservation: Reservation,
        restaurant: Restaurant,
    ) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)

        from tests.conftest import MenuItemFactory

        unavailable_item = cast(
            MenuItem,
            MenuItemFactory(
                restaurant=restaurant,
                menu__restaurant=restaurant,
                is_available=False,
            ),
        )

        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation, created_by=auth.user)
        session.participants.add(auth.user)

        url = reverse("cart-item-list", kwargs={"session_pk": session.public_id})
        response = auth.client.post(
            url,
            {"menu_item": str(unavailable_item.public_id), "quantity": 1},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["code"] == "menu_item_unavailable"


@pytest.mark.django_db(databases=["default"])
class TestGuestInit:
    url = reverse("guest-init")

    def test_guest_init_returns_token(
        self,
        api_client: Client,
        reservation: Reservation,
        restaurant: Restaurant,
    ) -> None:
        from apps.orders.models import CartSession

        CartSession.objects.create(restaurant=restaurant, reservation=reservation)

        response = api_client.post(
            self.url,
            {"device_id": "test-device-uuid", "reservation_id": str(reservation.public_id)},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access" in data
        assert len(data["access"]) > 0

    def test_guest_init_with_table_id(
        self,
        api_client: Client,
        reservation: Reservation,
        restaurant: Restaurant,
    ) -> None:
        from apps.orders.models import CartSession
        from apps.reservations.models import ReservationStatus

        reservation.status = ReservationStatus.ACTIVE
        reservation.start_at = datetime.now(UTC) - timedelta(minutes=30)
        reservation.save(update_fields=["status", "start_at"])
        _open_visit_session(reservation, restaurant)
        CartSession.objects.create(restaurant=restaurant, reservation=reservation)

        table = reservation.table
        assert table is not None

        response = api_client.post(
            self.url,
            {"device_id": "device-table", "table_id": str(table.public_id)},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access" in data

    def test_guest_init_table_id_creates_session_when_missing(
        self,
        api_client: Client,
        reservation: Reservation,
    ) -> None:
        from rest_framework_simplejwt.tokens import AccessToken

        from apps.orders.models import CartSession, CartSessionStatus
        from apps.reservations.models import ReservationStatus

        reservation.status = ReservationStatus.ACTIVE
        reservation.start_at = datetime.now(UTC) - timedelta(minutes=30)
        reservation.save(update_fields=["status", "start_at"])
        _open_visit_session(reservation, reservation.restaurant)

        table = reservation.table
        assert table is not None
        assert not CartSession.objects.exists()

        response = api_client.post(
            self.url,
            {"table_id": str(table.public_id)},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK

        sessions = CartSession.objects.filter(status=CartSessionStatus.ACTIVE)
        assert sessions.count() == 1
        session = sessions.get()
        assert session.reservation_id == reservation.id
        token = AccessToken(response.json()["access"])
        assert str(token["cart_session_id"]) == str(session.public_id)

    def test_guest_init_table_id_pending_booking_returns_not_yet_active(
        self,
        api_client: Client,
        reservation: Reservation,
    ) -> None:
        # A pending future booking exists but is not active yet: the guest is told
        # when it starts, not that there is no booking.
        from apps.orders.models import CartSession

        table = reservation.table
        assert table is not None

        response = api_client.post(
            self.url,
            {"table_id": str(table.public_id)},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        body = response.json()
        assert body["code"] == "RESERVATION_NOT_YET_ACTIVE"
        assert body["start_at"] == reservation.start_at.isoformat()
        assert not CartSession.objects.exists()

    def test_guest_init_table_id_no_booking_returns_404(
        self,
        api_client: Client,
        restaurant: Restaurant,
    ) -> None:
        # A table with no booking at all -> NO_ACTIVE_RESERVATION (unchanged).
        from apps.orders.models import CartSession

        bare_table = Table.objects.create(
            restaurant=restaurant,
            public_number="NB",
            capacity=2,
            zone=Zone.objects.create(restaurant=restaurant, name="Test Zone"),
            active=True,
        )

        response = api_client.post(
            self.url,
            {"table_id": str(bare_table.public_id)},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["code"] == "NO_ACTIVE_RESERVATION"
        assert not CartSession.objects.exists()

    def test_guest_init_table_id_skips_stale_reservation(
        self,
        api_client: Client,
        reservation: Reservation,
        second_reservation: Reservation,
        restaurant: Restaurant,
    ) -> None:
        from rest_framework_simplejwt.tokens import AccessToken

        from apps.orders.models import CartSession
        from apps.reservations.models import ReservationStatus

        table = reservation.table
        assert table is not None

        reservation.status = ReservationStatus.ACTIVE
        reservation.start_at = datetime.now(UTC) - timedelta(minutes=30)
        reservation.save(update_fields=["status", "start_at"])
        _open_visit_session(reservation, restaurant)
        active_session = CartSession.objects.create(restaurant=restaurant, reservation=reservation)

        second_reservation.status = ReservationStatus.COMPLETED
        second_reservation.save(update_fields=["status"])
        CartSession.objects.create(restaurant=restaurant, reservation=second_reservation)

        response = api_client.post(
            self.url,
            {"table_id": str(table.public_id)},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        token = AccessToken(response.json()["access"])
        assert str(token["cart_session_id"]) == str(active_session.public_id)

    def test_guest_init_token_cannot_touch_other_session(
        self,
        api_client: Client,
        reservation: Reservation,
        second_reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        from rest_framework.test import APIClient

        from apps.orders.models import CartSession
        from apps.reservations.models import ReservationStatus

        reservation.status = ReservationStatus.ACTIVE
        reservation.start_at = datetime.now(UTC) - timedelta(minutes=30)
        reservation.save(update_fields=["status", "start_at"])
        _open_visit_session(reservation, restaurant)
        table = reservation.table
        assert table is not None

        other_session = CartSession.objects.create(restaurant=restaurant, reservation=second_reservation)

        init_response = api_client.post(
            self.url,
            {"table_id": str(table.public_id)},
            content_type="application/json",
        )
        assert init_response.status_code == status.HTTP_200_OK
        token = init_response.json()["access"]

        guest_client = APIClient()
        guest_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        other_url = reverse("cart-item-list", kwargs={"session_pk": other_session.public_id})
        response = guest_client.post(
            other_url,
            {"menu_item": str(cart_item.public_id), "quantity": 1},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_guest_init_no_active_session_returns_404(
        self,
        api_client: Client,
        reservation: Reservation,
    ) -> None:
        response = api_client.post(
            self.url,
            {"device_id": "test-device-uuid", "reservation_id": str(reservation.public_id)},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_guest_init_without_device_id_succeeds(
        self,
        api_client: Client,
        reservation: Reservation,
        restaurant: Restaurant,
    ) -> None:
        from apps.orders.models import CartSession

        CartSession.objects.create(restaurant=restaurant, reservation=reservation)

        response = api_client.post(
            self.url,
            {"reservation_id": str(reservation.public_id)},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.json()

    def test_guest_init_reservation_id_reopens_cart_after_checkout(
        self,
        api_client: Client,
        reservation: Reservation,
        restaurant: Restaurant,
    ) -> None:
        from rest_framework_simplejwt.tokens import AccessToken

        from apps.orders.models import CartSession, CartSessionStatus
        from apps.reservations.models import ReservationStatus

        reservation.status = ReservationStatus.ACTIVE
        reservation.start_at = datetime.now(UTC) - timedelta(minutes=30)
        reservation.save(update_fields=["status", "start_at"])
        _open_visit_session(reservation, restaurant)
        # The previous round's cart was checked out and closed.
        closed = CartSession.objects.create(
            restaurant=restaurant,
            reservation=reservation,
            status=CartSessionStatus.CLOSED,
        )

        response = api_client.post(
            self.url,
            {"reservation_id": str(reservation.public_id)},
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_200_OK
        active = CartSession.objects.filter(reservation=reservation, status=CartSessionStatus.ACTIVE)
        assert active.count() == 1
        new_session = active.get()
        assert new_session.public_id != closed.public_id
        token = AccessToken(response.json()["access"])
        assert str(token["cart_session_id"]) == str(new_session.public_id)

    def test_guest_init_missing_target_returns_400(self, api_client: Client) -> None:
        response = api_client.post(
            self.url,
            {"device_id": "no-target"},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_guest_init_token_allows_add_item(
        self,
        api_client: Client,
        reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        from rest_framework.test import APIClient

        from apps.orders.models import CartSession

        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation)

        guest_response = api_client.post(
            self.url,
            {"device_id": "test-device-uuid", "reservation_id": str(reservation.public_id)},
            content_type="application/json",
        )
        assert guest_response.status_code == status.HTTP_200_OK
        token = guest_response.json()["access"]

        guest_client = APIClient()
        guest_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        url = reverse("cart-item-list", kwargs={"session_pk": session.public_id})
        response = guest_client.post(
            url,
            {"menu_item": str(cart_item.public_id), "quantity": 2, "guest_slot": 1},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["quantity"] == 2
        assert data["guest_slot"] == 1
        assert data["is_mine"] is True

    def test_guest_init_closed_session_returns_404(
        self,
        api_client: Client,
        reservation: Reservation,
        restaurant: Restaurant,
    ) -> None:
        from apps.orders.models import CartSession, CartSessionStatus

        CartSession.objects.create(
            restaurant=restaurant,
            reservation=reservation,
            status=CartSessionStatus.CLOSED,
        )

        response = api_client.post(
            self.url,
            {"device_id": "test-device-uuid", "reservation_id": str(reservation.public_id)},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db(databases=["default"])
class TestGuestSessionScope:
    """Guest token must be scoped to exactly one session."""

    def _issue_token(self, device_id: str, cart_session_id: str | None) -> str:
        from datetime import timedelta

        from rest_framework_simplejwt.tokens import AccessToken

        token = AccessToken()
        token.payload["is_guest"] = True
        token.payload["device_id"] = device_id
        if cart_session_id:
            token.payload["cart_session_id"] = cart_session_id
        token.set_exp(lifetime=timedelta(hours=4))
        return str(token)

    def test_guest_token_scoped_to_one_session(
        self,
        api_client: Client,
        reservation: Reservation,
        second_reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        from rest_framework.test import APIClient

        from apps.orders.models import CartSession

        session_a = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
        session_b = CartSession.objects.create(restaurant=restaurant, reservation=second_reservation)

        token = self._issue_token("device-a", str(session_a.public_id))
        guest_client = APIClient()
        guest_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        other_url = reverse("cart-item-list", kwargs={"session_pk": session_b.public_id})
        response = guest_client.post(
            other_url,
            {"menu_item": str(cart_item.public_id), "quantity": 1},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_guest_can_list_own_items(
        self,
        api_client: Client,
        reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        from rest_framework.test import APIClient

        from apps.orders.models import CartSession

        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation)

        token = self._issue_token("device-b", str(session.public_id))
        guest_client = APIClient()
        guest_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        add_url = reverse("cart-item-list", kwargs={"session_pk": session.public_id})
        add_resp = guest_client.post(
            add_url,
            {"menu_item": str(cart_item.public_id), "quantity": 2},
            content_type="application/json",
        )
        assert add_resp.status_code == status.HTTP_201_CREATED

        list_resp = guest_client.get(add_url)
        assert list_resp.status_code == status.HTTP_200_OK
        data = list_resp.json()
        assert data["count"] == 1
        assert data["results"][0]["quantity"] == 2

    def test_guest_list_other_session_rejected(
        self,
        api_client: Client,
        reservation: Reservation,
        second_reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        from rest_framework.test import APIClient

        from apps.orders.models import CartSession

        session_a = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
        session_b = CartSession.objects.create(restaurant=restaurant, reservation=second_reservation)

        token = self._issue_token("device-c", str(session_a.public_id))
        guest_client = APIClient()
        guest_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        add_url = reverse("cart-item-list", kwargs={"session_pk": session_a.public_id})
        add_resp = guest_client.post(
            add_url,
            {"menu_item": str(cart_item.public_id), "quantity": 2},
            content_type="application/json",
        )
        assert add_resp.status_code == status.HTTP_201_CREATED

        other_url = reverse("cart-item-list", kwargs={"session_pk": session_b.public_id})
        list_resp = guest_client.get(other_url)
        assert list_resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_guest_cannot_delete_from_other_session(
        self,
        api_client: Client,
        reservation: Reservation,
        second_reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        from rest_framework.test import APIClient

        from apps.orders.models import CartSession

        session_a = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
        session_b = CartSession.objects.create(restaurant=restaurant, reservation=second_reservation)
        other_item = CartItem.objects.create(
            cart_session=session_b,
            menu_item=cart_item,
            quantity=1,
            restaurant=restaurant,
        )

        token = self._issue_token("device-d", str(session_a.public_id))
        guest_client = APIClient()
        guest_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        delete_url = reverse("cart-item-detail", kwargs={"session_pk": session_b.public_id, "pk": other_item.public_id})
        response = guest_client.delete(delete_url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db(databases=["default"])
class TestGuestTokenEdgeCases:
    def _issue_token(self, device_id: str, cart_session_id: str | None, *, expired: bool = False) -> str:
        import time
        from datetime import timedelta

        from rest_framework_simplejwt.tokens import AccessToken

        token = AccessToken()
        token.payload["is_guest"] = True
        token.payload["device_id"] = device_id
        if cart_session_id:
            token.payload["cart_session_id"] = cart_session_id
        if expired:
            token.payload["exp"] = int(time.time()) - 3600
        else:
            token.set_exp(lifetime=timedelta(hours=4))
        return str(token)

    def test_expired_guest_token_returns_401(
        self,
        reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        from rest_framework.test import APIClient

        from apps.orders.models import CartSession

        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
        token = self._issue_token("device-exp", str(session.public_id), expired=True)
        guest_client = APIClient()
        guest_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        url = reverse("cart-item-list", kwargs={"session_pk": session.public_id})
        response = guest_client.post(
            url,
            {"menu_item": str(cart_item.public_id), "quantity": 1},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_malformed_guest_token_returns_401(
        self,
        reservation: Reservation,
        restaurant: Restaurant,
    ) -> None:
        from rest_framework.test import APIClient

        guest_client = APIClient()
        guest_client.credentials(HTTP_AUTHORIZATION="Bearer invalid.jwt.here")

        url = reverse("cart-item-list", kwargs={"session_pk": str(reservation.public_id)})
        response = guest_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_guest_reinit_carries_identity_forward(
        self,
        api_client: Client,
        reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        from rest_framework.test import APIClient

        from apps.orders.models import CartSession
        from tests.conftest import MenuItemFactory

        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
        second_item = cast(
            MenuItem,
            MenuItemFactory(restaurant=restaurant, menu__restaurant=restaurant, is_available=True),
        )

        resp1 = api_client.post(
            reverse("guest-init"),
            {"reservation_id": str(reservation.public_id)},
            content_type="application/json",
        )
        assert resp1.status_code == status.HTTP_200_OK
        token1 = resp1.json()["access"]

        url = reverse("cart-item-list", kwargs={"session_pk": session.public_id})
        client1 = APIClient()
        client1.credentials(HTTP_AUTHORIZATION=f"Bearer {token1}")
        add1 = client1.post(
            url,
            {"menu_item": str(cart_item.public_id), "quantity": 1},
            content_type="application/json",
        )
        assert add1.status_code == status.HTTP_201_CREATED
        assert add1.json()["is_mine"] is True
        slot = add1.json()["guest_slot"]

        resp2 = api_client.post(
            reverse("guest-init"),
            {"reservation_id": str(reservation.public_id)},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token1}",
        )
        assert resp2.status_code == status.HTTP_200_OK
        token2 = resp2.json()["access"]
        assert token2 != token1

        client2 = APIClient()
        client2.credentials(HTTP_AUTHORIZATION=f"Bearer {token2}")

        listed = client2.get(url)
        assert listed.status_code == status.HTTP_200_OK
        first = next(i for i in listed.json()["results"] if i["public_id"] == add1.json()["public_id"])
        assert first["is_mine"] is True

        add2 = client2.post(
            url,
            {"menu_item": str(second_item.public_id), "quantity": 1},
            content_type="application/json",
        )
        assert add2.status_code == status.HTTP_201_CREATED
        assert add2.json()["is_mine"] is True
        assert add2.json()["guest_slot"] == slot

    def test_guest_reinit_without_token_gets_new_identity(
        self,
        api_client: Client,
        reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        from rest_framework.test import APIClient

        from apps.orders.models import CartSession

        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation)
        url = reverse("cart-item-list", kwargs={"session_pk": session.public_id})

        resp1 = api_client.post(
            reverse("guest-init"),
            {"reservation_id": str(reservation.public_id)},
            content_type="application/json",
        )
        token1 = resp1.json()["access"]
        client1 = APIClient()
        client1.credentials(HTTP_AUTHORIZATION=f"Bearer {token1}")
        add1 = client1.post(
            url,
            {"menu_item": str(cart_item.public_id), "quantity": 1},
            content_type="application/json",
        )
        assert add1.status_code == status.HTTP_201_CREATED

        resp2 = api_client.post(
            reverse("guest-init"),
            {"reservation_id": str(reservation.public_id)},
            content_type="application/json",
        )
        token2 = resp2.json()["access"]
        client2 = APIClient()
        client2.credentials(HTTP_AUTHORIZATION=f"Bearer {token2}")
        listed = client2.get(url)
        first = next(i for i in listed.json()["results"] if i["public_id"] == add1.json()["public_id"])
        assert first["is_mine"] is False


@pytest.mark.django_db(databases=["default"])
class TestCartItemPatchUnavailable:
    """PATCH must reject requests for items that are no longer available."""

    def test_patch_unavailable_item_returns_400(
        self,
        api: Callable[..., AuthContext],
        reservation: Reservation,
        restaurant: Restaurant,
    ) -> None:
        from tests.conftest import MenuItemFactory

        item = cast(
            MenuItem,
            MenuItemFactory(
                restaurant=restaurant,
                menu__restaurant=restaurant,
                is_available=True,
            ),
        )

        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation, created_by=auth.user)
        session.participants.add(auth.user)

        # Add the item while available
        add_url = reverse("cart-item-list", kwargs={"session_pk": session.public_id})
        add_resp = auth.client.post(
            add_url,
            {"menu_item": str(item.public_id), "quantity": 2},
            content_type="application/json",
        )
        assert add_resp.status_code == status.HTTP_201_CREATED
        cart_item_id = add_resp.json()["public_id"]

        # Mark it unavailable
        item.is_available = False
        item.save(update_fields=["is_available"])

        # PATCH should now be rejected
        patch_url = reverse("cart-item-detail", kwargs={"session_pk": session.public_id, "pk": cart_item_id})
        response = auth.client.patch(
            patch_url,
            {"quantity": 5},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["code"] == "menu_item_unavailable"


@pytest.mark.django_db(transaction=True, databases=["default"])
class TestCartItemConcurrency:
    def test_concurrent_adds_combine_quantity(
        self,
        api: Callable[..., AuthContext],
        reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        import concurrent.futures

        from apps.orders.services import add_item_to_cart

        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation, created_by=auth.user)
        session.participants.add(auth.user)

        def add_item(quantity: int) -> int | None:
            close_old_connections()
            from django.db import transaction

            with transaction.atomic():
                try:
                    item = add_item_to_cart(
                        session=session,
                        menu_item_id=str(cart_item.public_id),
                        quantity=quantity,
                        user=auth.user,
                    )
                    return item.id
                except Exception:
                    return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            fut1 = executor.submit(add_item, 3)
            fut2 = executor.submit(add_item, 5)
            results = [fut1.result(), fut2.result()]

        assert all(r is not None for r in results)
        cart_items = CartItem.objects.filter(cart_session=session)
        assert cart_items.count() == 1
        first_item = cart_items.first()
        assert first_item is not None
        assert first_item.quantity == 8  # 3 + 5 = 8

    def test_concurrent_delete_and_update_has_valid_outcome(
        self,
        api: Callable[..., AuthContext],
        reservation: Reservation,
        restaurant: Restaurant,
        cart_item: MenuItem,
    ) -> None:
        import concurrent.futures

        from apps.orders.services import add_item_to_cart, remove_item_from_cart, update_cart_item_quantity

        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        session = CartSession.objects.create(restaurant=restaurant, reservation=reservation, created_by=auth.user)
        session.participants.add(auth.user)

        item = add_item_to_cart(
            session=session,
            menu_item_id=str(cart_item.public_id),
            quantity=5,
            user=auth.user,
        )
        item_id = str(item.public_id)

        results: dict[str, str | None] = {}

        def delete_item() -> None:
            close_old_connections()
            from django.db import transaction

            with transaction.atomic():
                try:
                    remove_item_from_cart(session=session, item_id=item_id, user=auth.user)
                    results["delete"] = "deleted"
                except Exception as exc:
                    results["delete"] = f"error:{type(exc).__name__}"

        def update_item() -> None:
            close_old_connections()
            from django.db import transaction

            with transaction.atomic():
                try:
                    update_cart_item_quantity(session=session, item_id=item_id, quantity=2, user=auth.user)
                    results["update"] = "updated"
                except Exception as exc:
                    results["update"] = f"error:{type(exc).__name__}"

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            fut1 = executor.submit(delete_item)
            fut2 = executor.submit(update_item)
            fut1.result()
            fut2.result()

        remaining = list(CartItem.objects.filter(cart_session=session))

        delete_outcome = results["delete"]
        update_outcome = results["update"]

        valid_outcomes = [
            # Delete won: item gone, update got 404
            (delete_outcome == "deleted" and update_outcome == "error:CartItemNotFoundError"),
            # Update won: quantity changed, then delete removed the item
            (delete_outcome == "deleted" and update_outcome == "updated"),
        ]
        assert any(valid_outcomes), f"Unexpected outcome: delete={delete_outcome}, update={update_outcome}"
        assert len(remaining) == 0, f"Cart should be empty, found {len(remaining)} items"
