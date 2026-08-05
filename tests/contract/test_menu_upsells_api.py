from collections.abc import Callable, Iterator
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.menu.models import Menu, MenuCategory, MenuItem
from apps.orders.models import Order, OrderItem, OrderStatus, Session, SessionStatus
from apps.reservations.models import Reservation
from apps.restaurants.models import Restaurant, Table

from ..conftest import MenuCategoryFactory as _MenuCategoryFactory
from ..conftest import MenuFactory as _MenuFactory
from ..conftest import MenuItemFactory as _MenuItemFactory
from ..conftest import RestaurantFactory as _RestaurantFactory

MenuFactory = cast(Callable[..., Menu], _MenuFactory)
MenuCategoryFactory = cast(Callable[..., MenuCategory], _MenuCategoryFactory)
MenuItemFactory = cast(Callable[..., MenuItem], _MenuItemFactory)
RestaurantFactory = cast(Callable[..., Restaurant], _RestaurantFactory)


def _create_completed_order(
    restaurant: Restaurant,
    table: Table,
    *items: MenuItem,
    waiter: Any = None,
    slot: int = 0,
) -> Order:
    """Create a completed order containing the given items (one line each).

    ``slot`` shifts the reservation window back in time so multiple orders can
    be created for the same table without violating the no-overlap constraint.
    """
    now = timezone.now()
    start = now - timedelta(hours=2) - timedelta(hours=slot * 2)
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=start,
        end_at=start + timedelta(hours=1),
    )
    session = Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        opened_by=waiter,
        guest_count=2,
        currency="UAH",
        opened_at=start,
        status=SessionStatus.CLOSED,
    )
    order = Order.objects.create(
        restaurant=restaurant,
        session=session,
        created_by=waiter,
        currency="UAH",
        status=OrderStatus.COMPLETED,
    )
    for index, item in enumerate(items, start=1):
        OrderItem.objects.create(
            restaurant=restaurant,
            order=order,
            menu_item=item,
            guest_slot=index,
            quantity=1,
            unit_price=item.price,
            total_price=item.price,
        )
    return order


@pytest.fixture(autouse=True)
def _restaurant_open() -> Iterator[None]:
    from unittest import mock

    with mock.patch("apps.orders.services.cart.is_restaurant_open", return_value=True):
        yield


@pytest.mark.django_db(databases=["default"])
class TestMenuUpsells:
    def test_unauthenticated_returns_200(
        self,
        api_client: Client,
        restaurant: Restaurant,
        menu: Menu,
        category: MenuCategory,
        item: MenuItem,
    ) -> None:
        companion = MenuItemFactory(menu=menu, category=category, restaurant=restaurant, name="Companion")
        url = reverse("menu-item-upsells", kwargs={"public_id": item.public_id})
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id)})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "count" in data
        assert "results" in data
        assert data["count"] == len(data["results"])
        assert data["results"][0]["name"] == companion.name

    def test_results_are_available_same_restaurant_and_exclude_target(
        self,
        api_client: Client,
        restaurant: Restaurant,
        menu: Menu,
        category: MenuCategory,
        item: MenuItem,
        table: Table,
    ) -> None:
        companion = MenuItemFactory(menu=menu, category=category, restaurant=restaurant, name="Companion")
        unavailable = MenuItemFactory(
            menu=menu,
            category=category,
            restaurant=restaurant,
            name="Unavailable",
            is_available=False,
        )
        other_restaurant = RestaurantFactory(name="Other")
        foreign = MenuItemFactory(name="Foreign item", restaurant=other_restaurant)
        _create_completed_order(restaurant, table, item, companion)

        url = reverse("menu-item-upsells", kwargs={"public_id": item.public_id})
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id)})

        assert response.status_code == status.HTTP_200_OK
        names = [r["name"] for r in response.json()["results"]]
        assert names == [companion.name]
        assert item.name not in names
        assert unavailable.name not in names
        assert foreign.name not in names

    def test_unavailable_target_returns_404(
        self,
        api_client: Client,
        restaurant: Restaurant,
        menu: Menu,
        category: MenuCategory,
    ) -> None:
        unavailable = MenuItemFactory(
            menu=menu,
            category=category,
            restaurant=restaurant,
            name="Unavailable Target",
            is_available=False,
        )
        url = reverse("menu-item-upsells", kwargs={"public_id": unavailable.public_id})
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id)})

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cooccurrence_ranks_above_unrelated(
        self,
        api_client: Client,
        restaurant: Restaurant,
        menu: Menu,
        category: MenuCategory,
        item: MenuItem,
        table: Table,
    ) -> None:
        frequently_ordered = MenuItemFactory(
            menu=menu,
            category=category,
            restaurant=restaurant,
            name="Frequently Ordered",
            sort_order=10,
        )
        unrelated = MenuItemFactory(
            menu=menu,
            category=category,
            restaurant=restaurant,
            name="Unrelated",
            sort_order=1,
        )
        # 3 completed orders pair item with frequently_ordered.
        for slot in range(3):
            _create_completed_order(restaurant, table, item, frequently_ordered, slot=slot)
        _create_completed_order(restaurant, table, unrelated, slot=3)

        url = reverse("menu-item-upsells", kwargs={"public_id": item.public_id})
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id)})

        names = [r["name"] for r in response.json()["results"]]
        assert names.index(frequently_ordered.name) < names.index(unrelated.name)

    def test_no_history_falls_back_to_dessert_drink_categories(
        self,
        api_client: Client,
        restaurant: Restaurant,
        menu: Menu,
        category: MenuCategory,
        item: MenuItem,
    ) -> None:
        other = MenuItemFactory(menu=menu, category=category, restaurant=restaurant, name="Mains Dish", sort_order=1)
        dessert_cat = MenuCategoryFactory(menu=menu, name="Desserts")
        dessert = MenuItemFactory(
            menu=menu,
            category=dessert_cat,
            restaurant=restaurant,
            name="Cheesecake",
            sort_order=50,
        )
        # No orders at all -> fallback path.
        url = reverse("menu-item-upsells", kwargs={"public_id": item.public_id})
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id)})

        assert response.status_code == status.HTTP_200_OK
        names = [r["name"] for r in response.json()["results"]]
        assert len(names) > 0
        assert names.index(dessert.name) < names.index(other.name)

    def test_no_history_fallback_matches_ukrainian_dessert_drink_categories(
        self,
        api_client: Client,
        restaurant: Restaurant,
        menu: Menu,
        category: MenuCategory,
        item: MenuItem,
    ) -> None:
        main = MenuItemFactory(menu=menu, category=category, restaurant=restaurant, name="Основна страва", sort_order=1)
        dessert_cat = MenuCategoryFactory(menu=menu, name="Десерти")
        dessert = MenuItemFactory(
            menu=menu,
            category=dessert_cat,
            restaurant=restaurant,
            name="Чізкейк",
            sort_order=50,
        )
        drink_cat = MenuCategoryFactory(menu=menu, name="Напої")
        drink = MenuItemFactory(
            menu=menu,
            category=drink_cat,
            restaurant=restaurant,
            name="Лимонад",
            sort_order=60,
        )
        url = reverse("menu-item-upsells", kwargs={"public_id": item.public_id})
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id)})

        assert response.status_code == status.HTTP_200_OK
        names = [r["name"] for r in response.json()["results"]]
        assert names.index(dessert.name) < names.index(main.name)
        assert names.index(drink.name) < names.index(main.name)

    def test_unknown_restaurant_returns_404(self, api_client: Client, item: MenuItem) -> None:
        url = reverse("menu-item-upsells", kwargs={"public_id": item.public_id})
        response: Any = api_client.get(url, {"restaurant": "00000000-0000-0000-0000-000000000000"})
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_dish_from_another_restaurant_returns_404(
        self,
        api_client: Client,
        restaurant: Restaurant,
        item: MenuItem,
    ) -> None:
        other = RestaurantFactory(name="Other")
        url = reverse("menu-item-upsells", kwargs={"public_id": item.public_id})
        response: Any = api_client.get(url, {"restaurant": str(other.public_id)})
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_results_capped_at_six(
        self,
        api_client: Client,
        restaurant: Restaurant,
        menu: Menu,
        category: MenuCategory,
        item: MenuItem,
    ) -> None:
        for index in range(8):
            MenuItemFactory(
                menu=menu,
                category=category,
                restaurant=restaurant,
                name=f"Item {index}",
            )
        url = reverse("menu-item-upsells", kwargs={"public_id": item.public_id})
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id)})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()["results"]) <= 6

    def test_guest_token_annotates_is_liked(
        self,
        api_client: Client,
        restaurant: Restaurant,
        menu: Menu,
        category: MenuCategory,
        item: MenuItem,
    ) -> None:
        companion = MenuItemFactory(menu=menu, category=category, restaurant=restaurant, name="Companion")
        from apps.menu.models import MenuItemLike

        MenuItemLike.objects.create(
            restaurant=restaurant,
            menu_item=companion,
            guest_token="guest-1",
        )
        url = reverse("menu-item-upsells", kwargs={"public_id": item.public_id})
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id), "guest_token": "guest-1"})

        assert response.status_code == status.HTTP_200_OK
        results = response.json()["results"]
        liked = [r for r in results if r["name"] == companion.name]
        assert liked and liked[0]["is_liked"] is True

    def test_waiter_authenticated_returns_same_shape(
        self,
        restaurant: Restaurant,
        menu: Menu,
        category: MenuCategory,
        item: MenuItem,
        api: Callable[..., Any],
    ) -> None:
        companion = MenuItemFactory(menu=menu, category=category, restaurant=restaurant, name="Companion")
        client, _ = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
        url = reverse("menu-item-upsells", kwargs={"public_id": item.public_id})
        response: Any = client.get(url, {"restaurant": str(restaurant.public_id)})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "count" in data and "results" in data
        assert data["results"][0]["name"] == companion.name

    def test_new_completed_order_updates_ranking(
        self,
        api_client: Client,
        restaurant: Restaurant,
        menu: Menu,
        category: MenuCategory,
        item: MenuItem,
        table: Table,
    ) -> None:
        promoted = MenuItemFactory(menu=menu, category=category, restaurant=restaurant, name="Promoted", sort_order=5)
        demoted = MenuItemFactory(menu=menu, category=category, restaurant=restaurant, name="Demoted", sort_order=1)
        _create_completed_order(restaurant, table, item, demoted)
        url = reverse("menu-item-upsells", kwargs={"public_id": item.public_id})

        first_response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id)})
        first_names = [r["name"] for r in first_response.json()["results"]]
        assert first_names.index(demoted.name) < first_names.index(promoted.name)

        # A new completed order pairs item with promoted -> ranking flips.
        _create_completed_order(restaurant, table, item, promoted, slot=1)
        _create_completed_order(restaurant, table, item, promoted, slot=2)
        second_response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id)})
        second_names = [r["name"] for r in second_response.json()["results"]]
        assert second_names.index(promoted.name) < second_names.index(demoted.name)

    def test_voided_and_non_completed_orders_do_not_contribute(
        self,
        api_client: Client,
        restaurant: Restaurant,
        menu: Menu,
        category: MenuCategory,
        item: MenuItem,
        table: Table,
    ) -> None:
        from apps.orders.models import OrderItemStatus

        real_pair = MenuItemFactory(menu=menu, category=category, restaurant=restaurant, name="Real Pair")
        void_item = MenuItemFactory(menu=menu, category=category, restaurant=restaurant, name="Voided Pair")
        draft_item = MenuItemFactory(menu=menu, category=category, restaurant=restaurant, name="Draft Pair")

        now = timezone.now()
        reservation = Reservation.objects.create(
            restaurant=restaurant,
            table=table,
            guest_count=2,
            start_at=now - timedelta(hours=2),
            end_at=now - timedelta(hours=1),
        )
        session = Session.objects.create(
            restaurant=restaurant,
            table=table,
            reservation=reservation,
            guest_count=2,
            currency="UAH",
            opened_at=now - timedelta(hours=2),
            status=SessionStatus.CLOSED,
        )
        voided_order = Order.objects.create(
            restaurant=restaurant,
            session=session,
            currency="UAH",
            status=OrderStatus.COMPLETED,
        )
        OrderItem.objects.create(
            restaurant=restaurant,
            order=voided_order,
            menu_item=item,
            guest_slot=1,
            quantity=1,
            unit_price=item.price,
        )
        OrderItem.objects.create(
            restaurant=restaurant,
            order=voided_order,
            menu_item=void_item,
            guest_slot=2,
            quantity=1,
            unit_price=Decimal("10.0000"),
            voided_at=now,
            status=OrderItemStatus.VOIDED,
        )
        draft_order = Order.objects.create(
            restaurant=restaurant,
            session=session,
            currency="UAH",
            status=OrderStatus.DRAFT,
        )
        OrderItem.objects.create(
            restaurant=restaurant,
            order=draft_order,
            menu_item=item,
            guest_slot=1,
            quantity=1,
            unit_price=item.price,
        )
        OrderItem.objects.create(
            restaurant=restaurant,
            order=draft_order,
            menu_item=draft_item,
            guest_slot=2,
            quantity=1,
            unit_price=Decimal("10.0000"),
        )
        # A genuine completed pairing drives the co-occurrence path.
        _create_completed_order(restaurant, table, item, real_pair, slot=1)

        url = reverse("menu-item-upsells", kwargs={"public_id": item.public_id})
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id)})

        names = [r["name"] for r in response.json()["results"]]
        assert names.index(real_pair.name) < names.index(void_item.name)
        assert names.index(real_pair.name) < names.index(draft_item.name)
