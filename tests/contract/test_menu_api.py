from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse
from rest_framework import status

from apps.menu.models import Menu, MenuCategory, MenuItem
from apps.restaurants.models import Restaurant


@pytest.fixture
def api_client() -> Client:
    return Client()


@pytest.fixture
def restaurant() -> Restaurant:
    return Restaurant.objects.create(name="Test Restaurant", address="123 Main St")


@pytest.fixture
def menu(restaurant: Restaurant) -> Menu:
    return Menu.objects.create(restaurant=restaurant, name="Dinner", is_active=True)


@pytest.fixture
def category(menu: Menu) -> MenuCategory:
    return MenuCategory.objects.create(menu=menu, name="Mains", sort_order=1)


@pytest.fixture
def item(menu: Menu, category: MenuCategory, restaurant: Restaurant) -> MenuItem:
    return MenuItem.objects.create(
        restaurant=restaurant,
        menu=menu,
        category=category,
        name="Steak",
        description="Grilled to perfection",
        price=Decimal("29.9900"),
        sort_order=1,
    )


@pytest.mark.django_db(databases=["default"])
class TestPublicMenuCategories:
    def test_unauthenticated_returns_200(
        self, api_client: Client, menu: Menu, category: MenuCategory, item: MenuItem
    ) -> None:
        url = reverse("menu-category-list")
        response: Any = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data["results"]
        assert len(results) >= 1
        assert results[0]["name"] == "Mains"
        assert results[0]["public_id"] == str(category.public_id)

    def test_filter_by_menu(self, api_client: Client, menu: Menu, category: MenuCategory, item: MenuItem) -> None:
        url = reverse("menu-category-list")
        response: Any = api_client.get(url, {"menu": menu.pk})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data["results"]
        assert len(results) == 1
        assert results[0]["name"] == "Mains"


@pytest.mark.django_db(databases=["default"])
class TestPublicMenuItems:
    def test_unauthenticated_returns_200(
        self, api_client: Client, menu: Menu, category: MenuCategory, item: MenuItem
    ) -> None:
        url = reverse("menu-item-list")
        response: Any = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data["results"]
        assert len(results) >= 1
        assert results[0]["name"] == "Steak"
        assert results[0]["price"] == "29.9900"
        assert results[0]["is_available"] is True
        assert results[0]["public_id"] == str(item.public_id)

    def test_filter_by_category(self, api_client: Client, menu: Menu, category: MenuCategory, item: MenuItem) -> None:
        url = reverse("menu-item-list")
        response: Any = api_client.get(url, {"category": category.pk})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data["results"]
        assert len(results) == 1
        assert results[0]["name"] == "Steak"

    def test_unavailable_item_hidden(
        self, api_client: Client, menu: Menu, category: MenuCategory, item: MenuItem
    ) -> None:
        item.is_available = False
        item.save()

        url = reverse("menu-item-list")
        response: Any = api_client.get(url, {"is_available": "false"})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data["results"]
        assert len(results) == 1
        assert results[0]["is_available"] is False


@pytest.mark.django_db(databases=["default"])
class TestPublicMenuMenus:
    def test_unauthenticated_returns_200(self, api_client: Client, menu: Menu) -> None:
        url = reverse("menu-list")
        response: Any = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data["results"]
        assert len(results) >= 1
        assert results[0]["name"] == "Dinner"
        assert results[0]["public_id"] == str(menu.public_id)
