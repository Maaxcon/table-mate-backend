from collections.abc import Callable
from decimal import Decimal
from typing import Any, cast

import pytest
from django.test import Client
from django.urls import reverse
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.menu.models import Menu, MenuCategory, MenuItem
from apps.restaurants.models import Restaurant

from ..conftest import MenuCategoryFactory as _MenuCategoryFactory
from ..conftest import MenuFactory as _MenuFactory
from ..conftest import MenuItemFactory as _MenuItemFactory

MenuFactory = cast(Callable[..., Menu], _MenuFactory)
MenuCategoryFactory = cast(Callable[..., MenuCategory], _MenuCategoryFactory)
MenuItemFactory = cast(Callable[..., MenuItem], _MenuItemFactory)


@pytest.mark.django_db(databases=["default"])
class TestPublicMenuCategories:
    def test_unauthenticated_returns_200(
        self, api_client: Client, restaurant: Restaurant, menu: Menu, category: MenuCategory
    ) -> None:
        url = reverse("menu-category-list")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id)})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data["results"]
        assert len(results) >= 1
        assert results[0]["name"] == "Mains"
        assert results[0]["public_id"] == str(category.public_id)
        assert results[0]["color"] == "#F97316"

    def test_filter_by_menu(
        self, api_client: Client, restaurant: Restaurant, menu: Menu, category: MenuCategory
    ) -> None:
        other_menu = MenuFactory(restaurant=restaurant, name="Other")
        MenuCategoryFactory(menu=other_menu, name="Should not appear")
        url = reverse("menu-category-list")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id), "menu": str(menu.public_id)})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data["results"]
        assert len(results) == 1
        assert results[0]["name"] == "Mains"

    def test_empty_database_returns_empty_results(self, api_client: Client, empty_restaurant: Restaurant) -> None:
        url = reverse("menu-category-list")
        response: Any = api_client.get(url, {"restaurant": str(empty_restaurant.public_id)})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == 0
        assert data["results"] == []

    def test_ordering_by_name(self, api_client: Client, restaurant: Restaurant, menu: Menu) -> None:
        MenuCategoryFactory(menu=menu, name="A", sort_order=2)
        MenuCategoryFactory(menu=menu, name="B", sort_order=1)
        url = reverse("menu-category-list")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id), "ordering": "name"})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        names = [r["name"] for r in data["results"]]
        assert names == sorted(names)

    def test_pagination_response_structure(
        self, api_client: Client, restaurant: Restaurant, category: MenuCategory
    ) -> None:
        url = reverse("menu-category-list")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id)})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "count" in data
        assert "next" in data
        assert "previous" in data
        assert "results" in data


@pytest.mark.django_db(databases=["default"])
class TestPublicMenuItems:
    def test_unauthenticated_returns_200(
        self, api_client: Client, restaurant: Restaurant, menu: Menu, category: MenuCategory, item: MenuItem
    ) -> None:
        url = reverse("menu-item-list")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id)})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data["results"]
        assert len(results) >= 1
        assert results[0]["name"] == "Steak"
        assert results[0]["price"] == "29.9900"
        assert isinstance(results[0]["allergens"], list)
        assert results[0]["is_available"] is True
        assert results[0]["likes_count"] == 0
        assert results[0]["is_liked"] is False
        assert results[0]["public_id"] == str(item.public_id)

    def test_filter_by_category(
        self, api_client: Client, restaurant: Restaurant, menu: Menu, category: MenuCategory, item: MenuItem
    ) -> None:
        url = reverse("menu-item-list")
        response: Any = api_client.get(
            url, {"restaurant": str(restaurant.public_id), "category": str(category.public_id)}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data["results"]
        assert len(results) == 1
        assert results[0]["name"] == "Steak"

    def test_filter_by_is_available_false(
        self, api_client: Client, restaurant: Restaurant, menu: Menu, category: MenuCategory, item: MenuItem
    ) -> None:
        item.is_available = False
        item.save()

        url = reverse("menu-item-list")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id), "is_available": "false"})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data["results"]
        assert len(results) == 1
        assert results[0]["is_available"] is False

    def test_filter_by_is_available_true(
        self, api_client: Client, restaurant: Restaurant, menu: Menu, category: MenuCategory, item: MenuItem
    ) -> None:
        url = reverse("menu-item-list")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id), "is_available": "true"})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data["results"]
        assert len(results) >= 1
        assert results[0]["is_available"] is True

    def test_empty_database_returns_empty_results(self, api_client: Client, empty_restaurant: Restaurant) -> None:
        url = reverse("menu-item-list")
        response: Any = api_client.get(url, {"restaurant": str(empty_restaurant.public_id)})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == 0
        assert data["results"] == []

    def test_ordering_by_name(
        self, api_client: Client, restaurant: Restaurant, menu: Menu, category: MenuCategory
    ) -> None:
        MenuItemFactory(
            restaurant=restaurant, menu=menu, category=category, name="B", price=Decimal("10.0000"), sort_order=2
        )
        MenuItemFactory(
            restaurant=restaurant, menu=menu, category=category, name="A", price=Decimal("20.0000"), sort_order=1
        )
        url = reverse("menu-item-list")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id), "ordering": "name"})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        names = [r["name"] for r in data["results"]]
        assert names == sorted(names)

    def test_pagination_response_structure(self, api_client: Client, restaurant: Restaurant, item: MenuItem) -> None:
        url = reverse("menu-item-list")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id)})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "count" in data
        assert "next" in data
        assert "previous" in data
        assert "results" in data


@pytest.mark.django_db(databases=["default"])
class TestPublicMenuMenus:
    def test_unauthenticated_returns_200(self, api_client: Client, restaurant: Restaurant, menu: Menu) -> None:
        url = reverse("menu-list")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id)})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data["results"]
        assert len(results) >= 1
        assert results[0]["name"] == "Dinner"
        assert results[0]["public_id"] == str(menu.public_id)

    def test_empty_database_returns_empty_results(self, api_client: Client, empty_restaurant: Restaurant) -> None:
        url = reverse("menu-list")
        response: Any = api_client.get(url, {"restaurant": str(empty_restaurant.public_id)})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == 0
        assert data["results"] == []

    def test_ordering_by_name(self, api_client: Client, restaurant: Restaurant) -> None:
        MenuFactory(restaurant=restaurant, name="A", is_active=True)
        MenuFactory(restaurant=restaurant, name="B", is_active=True)
        url = reverse("menu-list")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id), "ordering": "name"})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        names = [r["name"] for r in data["results"]]
        assert names == sorted(names)

    def test_pagination_response_structure(self, api_client: Client, restaurant: Restaurant, menu: Menu) -> None:
        url = reverse("menu-list")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id)})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "count" in data
        assert "next" in data
        assert "previous" in data
        assert "results" in data


@pytest.mark.django_db(databases=["default"])
class TestAdminMenuCategories:
    def test_admin_list_with_menu_filter_returns_200(
        self,
        api: Any,
        restaurant: Restaurant,
        menu: Menu,
        category: MenuCategory,
    ) -> None:
        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        url = reverse("admin-menu-category-list")
        response: Any = auth.client.get(url, {"menu": str(menu.public_id), "ordering": "sort_order"})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["results"][0]["public_id"] == str(category.public_id)
        assert data["results"][0]["color"] == "#F97316"

    def test_admin_can_update_category_color(
        self,
        api: Any,
        restaurant: Restaurant,
        menu: Menu,
        category: MenuCategory,
    ) -> None:
        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        url = reverse("admin-menu-category-detail", kwargs={"public_id": str(category.public_id)})
        response: Any = auth.client.patch(
            url,
            data={"color": "#123ABC"},
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert payload["color"] == "#123ABC"
        category.refresh_from_db()
        assert category.color == "#123ABC"


@pytest.mark.django_db(databases=["default"])
class TestAdminMenuItems:
    def test_admin_list_with_menu_filter_returns_200(
        self,
        api: Any,
        restaurant: Restaurant,
        menu: Menu,
        item: MenuItem,
    ) -> None:
        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        url = reverse("admin-menu-item-list")
        response: Any = auth.client.get(url, {"menu": str(menu.public_id), "ordering": "sort_order"})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["results"][0]["public_id"] == str(item.public_id)


@pytest.mark.django_db(databases=["default"])
class TestMenuItemSearch:
    def test_search_returns_matching_items(
        self, api_client: Client, restaurant: Restaurant, menu: Menu, category: MenuCategory
    ) -> None:
        MenuItemFactory(
            restaurant=restaurant,
            menu=menu,
            category=category,
            name="Margherita Pizza",
            description="Classic tomato and mozzarella",
            is_available=True,
        )
        MenuItemFactory(
            restaurant=restaurant,
            menu=menu,
            category=category,
            name="Pepperoni",
            description="Spicy salami pizza",
            is_available=True,
        )
        MenuItemFactory(
            restaurant=restaurant,
            menu=menu,
            category=category,
            name="Caesar Salad",
            description="Romaine with parmesan",
            is_available=True,
        )

        url = reverse("menu-item-search")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id), "q": "pizza"})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        names = [r["name"] for r in data["results"]]
        assert "Margherita Pizza" in names
        assert "Pepperoni" in names
        assert "Caesar Salad" not in names

    def test_search_empty_q_returns_empty_paginated_response(
        self, api_client: Client, restaurant: Restaurant, item: MenuItem
    ) -> None:
        url = reverse("menu-item-search")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id), "q": ""})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == 0
        assert data["results"] == []

    def test_search_accessible_without_authentication(
        self, api_client: Client, restaurant: Restaurant, menu: Menu, category: MenuCategory
    ) -> None:
        MenuItemFactory(
            restaurant=restaurant,
            menu=menu,
            category=category,
            name="Burger",
            description="Beef patty",
            is_available=True,
        )
        url = reverse("menu-item-search")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id), "q": "Burger"})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["name"] == "Burger"


@pytest.mark.django_db(databases=["default"])
class TestMenuItemLikes:
    def test_toggle_like_adds_and_removes_like(
        self, api_client: Client, restaurant: Restaurant, item: MenuItem
    ) -> None:
        toggle_url = (
            reverse("menu-item-toggle-like", kwargs={"public_id": str(item.public_id)})
            + f"?restaurant={restaurant.public_id}"
        )
        list_url = reverse("menu-item-list")
        guest_token = "guest-like-token-1"

        like_response: Any = api_client.post(
            toggle_url,
            data={"guest_token": guest_token},
            content_type="application/json",
        )
        assert like_response.status_code == status.HTTP_200_OK
        like_data = like_response.json()
        assert like_data["is_liked"] is True
        assert like_data["likes_count"] == 1

        list_response: Any = api_client.get(
            list_url,
            {"restaurant": str(restaurant.public_id), "guest_token": guest_token},
        )
        assert list_response.status_code == status.HTTP_200_OK
        list_item = list_response.json()["results"][0]
        assert list_item["public_id"] == str(item.public_id)
        assert list_item["likes_count"] == 1
        assert list_item["is_liked"] is True

        unlike_response: Any = api_client.post(
            toggle_url,
            data={"guest_token": guest_token},
            content_type="application/json",
        )
        assert unlike_response.status_code == status.HTTP_200_OK
        unlike_data = unlike_response.json()
        assert unlike_data["is_liked"] is False
        assert unlike_data["likes_count"] == 0

    def test_like_state_is_personalized_by_guest_token(
        self, api_client: Client, restaurant: Restaurant, item: MenuItem
    ) -> None:
        toggle_url = (
            reverse("menu-item-toggle-like", kwargs={"public_id": str(item.public_id)})
            + f"?restaurant={restaurant.public_id}"
        )
        list_url = reverse("menu-item-list")
        api_client.post(
            toggle_url,
            data={"guest_token": "guest-a"},
            content_type="application/json",
        )

        response_for_a: Any = api_client.get(
            list_url,
            {"restaurant": str(restaurant.public_id), "guest_token": "guest-a"},
        )
        response_for_b: Any = api_client.get(
            list_url,
            {"restaurant": str(restaurant.public_id), "guest_token": "guest-b"},
        )
        assert response_for_a.status_code == status.HTTP_200_OK
        assert response_for_b.status_code == status.HTTP_200_OK
        assert response_for_a.json()["results"][0]["is_liked"] is True
        assert response_for_a.json()["results"][0]["likes_count"] == 1
        assert response_for_b.json()["results"][0]["is_liked"] is False
        assert response_for_b.json()["results"][0]["likes_count"] == 1
