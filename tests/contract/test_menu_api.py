from collections.abc import Callable
from decimal import Decimal
from typing import Any, cast

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.menu.models import Allergen, Menu, MenuCategory, MenuItem, MenuItemLike
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

    def test_filters_by_allergens_and_ingredients(
        self, api_client: Client, restaurant: Restaurant, menu: Menu, category: MenuCategory
    ) -> None:
        excluded = MenuItemFactory(
            restaurant=restaurant,
            menu=menu,
            category=category,
            name="Tomato pasta",
            ingredients=["Tomato", "Basil"],
            allergens=["Глютен", "Молоко"],
        )
        matching = MenuItemFactory(
            restaurant=restaurant,
            menu=menu,
            category=category,
            name="Tomato salad",
            ingredients=["Tomato"],
            allergens=["Риба"],
        )
        url = reverse("menu-item-list")
        response: Any = api_client.get(
            url,
            {
                "restaurant": str(restaurant.public_id),
                "allergens": ["Глютен", "Молоко"],
                "ingredients": "Tomato",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        results = response.json()["results"]
        assert [result["public_id"] for result in results] == [str(matching.public_id)]
        assert str(excluded.public_id) not in [result["public_id"] for result in results]

        response = api_client.get(url, {"restaurant": str(restaurant.public_id), "ingredients": ","})

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["results"] == []

    def test_rejects_unknown_allergen_filter(
        self, api_client: Client, restaurant: Restaurant, menu: Menu, category: MenuCategory
    ) -> None:
        url = reverse("menu-item-list")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id), "allergens": "Unknown"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_orders_by_popularity(
        self, api_client: Client, restaurant: Restaurant, menu: Menu, category: MenuCategory
    ) -> None:
        popular = MenuItemFactory(restaurant=restaurant, menu=menu, category=category, name="Popular")
        less_popular = MenuItemFactory(restaurant=restaurant, menu=menu, category=category, name="Less popular")
        for guest_token in ("guest-1", "guest-2"):
            MenuItemLike.objects.create(menu_item=popular, restaurant=restaurant, guest_token=guest_token)
        MenuItemLike.objects.create(menu_item=less_popular, restaurant=restaurant, guest_token="guest-3")

        url = reverse("menu-item-list")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id), "ordering": "-likes_count"})

        assert response.status_code == status.HTTP_200_OK
        results = response.json()["results"]
        assert [result["public_id"] for result in results[:2]] == [
            str(popular.public_id),
            str(less_popular.public_id),
        ]

    def test_price_ordering_is_opt_in(
        self, api_client: Client, restaurant: Restaurant, menu: Menu, category: MenuCategory
    ) -> None:
        cheapest = MenuItemFactory(
            restaurant=restaurant, menu=menu, category=category, name="Cheapest", price=Decimal("1.0000")
        )
        priciest = MenuItemFactory(
            restaurant=restaurant, menu=menu, category=category, name="Priciest", price=Decimal("100.0000")
        )
        url = reverse("menu-item-list")

        ascending: Any = api_client.get(url, {"restaurant": str(restaurant.public_id), "ordering": "price"})
        descending: Any = api_client.get(url, {"restaurant": str(restaurant.public_id), "ordering": "-price"})

        assert ascending.status_code == status.HTTP_200_OK
        assert descending.status_code == status.HTTP_200_OK
        assert ascending.json()["results"][0]["public_id"] == str(cheapest.public_id)
        assert descending.json()["results"][0]["public_id"] == str(priciest.public_id)

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
class TestAllergenCatalog:
    def test_public_list_reads_database_catalog(self, api_client: Client) -> None:
        Allergen.objects.create(name="Custom allergen")

        response: Any = api_client.get(reverse("allergens"))

        assert response.status_code == status.HTTP_200_OK
        assert "Custom allergen" in response.json()

    def test_admin_cannot_modify_global_catalog(self, api: Any, restaurant: Restaurant) -> None:
        allergen = Allergen.objects.create(name="Custom allergen")
        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        create_allergen: Any = auth.client.post(
            reverse("admin-allergen-list"),
            data={"name": "Another allergen"},
            content_type="application/json",
        )
        update_allergen: Any = auth.client.patch(
            reverse("admin-allergen-detail", kwargs={"public_id": allergen.public_id}),
            data={"name": "Renamed allergen"},
            content_type="application/json",
        )
        delete_allergen: Any = auth.client.delete(
            reverse("admin-allergen-detail", kwargs={"public_id": allergen.public_id})
        )

        assert create_allergen.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert update_allergen.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert delete_allergen.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        allergen.refresh_from_db()
        assert allergen.name == "Custom allergen"


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

    def test_direct_orm_write_rejects_invalid_color(
        self,
        menu: Menu,
    ) -> None:
        # The field validator only fires at the serializer/admin layer; save() must
        # also reject an unvalidated value written straight through the ORM.
        with pytest.raises(ValidationError):
            MenuCategory.objects.create(menu=menu, name="Bad", color="red; }")


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

    def test_search_matches_category_name(
        self, api_client: Client, restaurant: Restaurant, menu: Menu, category: MenuCategory
    ) -> None:
        MenuItemFactory(
            restaurant=restaurant,
            menu=menu,
            category=category,
            name="Ribeye Steak",
            description="Grilled to order",
            is_available=True,
        )

        url = reverse("menu-item-search")
        response: Any = api_client.get(url, {"restaurant": str(restaurant.public_id), "q": category.name})

        assert response.status_code == status.HTTP_200_OK
        names = [r["name"] for r in response.json()["results"]]
        assert "Ribeye Steak" in names

    def test_search_orders_by_price(
        self, api_client: Client, restaurant: Restaurant, menu: Menu, category: MenuCategory
    ) -> None:
        for name, price in [("Pizza Cheap", 80), ("Pizza Mid", 150), ("Pizza Pricey", 300)]:
            MenuItemFactory(
                restaurant=restaurant,
                menu=menu,
                category=category,
                name=name,
                price=price,
                is_available=True,
            )

        url = reverse("menu-item-search")
        asc: Any = api_client.get(url, {"restaurant": str(restaurant.public_id), "q": "pizza", "ordering": "price"})
        desc: Any = api_client.get(url, {"restaurant": str(restaurant.public_id), "q": "pizza", "ordering": "-price"})

        assert asc.status_code == status.HTTP_200_OK
        assert [r["name"] for r in asc.json()["results"]] == [
            "Pizza Cheap",
            "Pizza Mid",
            "Pizza Pricey",
        ]
        assert [r["name"] for r in desc.json()["results"]] == [
            "Pizza Pricey",
            "Pizza Mid",
            "Pizza Cheap",
        ]

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
