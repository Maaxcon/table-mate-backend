from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse
from rest_framework import status

from apps.menu.models import Menu, MenuCategory, MenuItem
from apps.restaurants.models import Restaurant

from ..conftest import MenuCategoryFactory, MenuFactory, MenuItemFactory


@pytest.mark.django_db(databases=["default"])
class TestPublicMenuCategories:
    def test_unauthenticated_returns_200(
        self, api_client: Client, restaurant: Restaurant, menu: Menu, category: MenuCategory, item: MenuItem
    ) -> None:
        url = reverse("menu-category-list")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id)})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data["results"]
        assert len(results) >= 1
        assert results[0]["name"] == "Mains"
        assert results[0]["public_id"] == str(category.public_id)

    def test_filter_by_menu(
        self, api_client: Client, restaurant: Restaurant, menu: Menu, category: MenuCategory, item: MenuItem
    ) -> None:
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
        assert results[0]["is_available"] is True
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
