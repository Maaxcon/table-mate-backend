from collections.abc import Callable
from typing import Any, cast

import pytest
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
class TestAdminMenuItemBulk:
    def _admin(self, api: Callable[..., Any], restaurant: Restaurant) -> Any:
        return api(role=RoleCode.ADMIN, restaurant_id=restaurant.id).client

    def test_set_available_hides_many_items(
        self, api: Callable[..., Any], restaurant: Restaurant, menu: Menu, category: MenuCategory
    ) -> None:
        a = MenuItemFactory(menu=menu, category=category, restaurant=restaurant, is_available=True)
        b = MenuItemFactory(menu=menu, category=category, restaurant=restaurant, is_available=True)
        client = self._admin(api, restaurant)

        response: Any = client.post(
            reverse("admin-menu-item-bulk"),
            {"ids": [str(a.public_id), str(b.public_id)], "action": "set_available", "is_available": False},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"updated": 2}
        a.refresh_from_db()
        b.refresh_from_db()
        assert a.is_available is False
        assert b.is_available is False

    def test_set_category_moves_items(
        self, api: Callable[..., Any], restaurant: Restaurant, menu: Menu, category: MenuCategory
    ) -> None:
        target = MenuCategoryFactory(menu=menu, name="Desserts", sort_order=2)
        item = MenuItemFactory(menu=menu, category=category, restaurant=restaurant)
        client = self._admin(api, restaurant)

        response: Any = client.post(
            reverse("admin-menu-item-bulk"),
            {"ids": [str(item.public_id)], "action": "set_category", "category": str(target.public_id)},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        item.refresh_from_db()
        assert item.category_id == target.id

    def test_set_category_null_clears_category(
        self, api: Callable[..., Any], restaurant: Restaurant, menu: Menu, category: MenuCategory
    ) -> None:
        item = MenuItemFactory(menu=menu, category=category, restaurant=restaurant)
        client = self._admin(api, restaurant)

        response: Any = client.post(
            reverse("admin-menu-item-bulk"),
            {"ids": [str(item.public_id)], "action": "set_category", "category": None},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        item.refresh_from_db()
        assert item.category_id is None

    def test_set_category_rejects_category_from_another_menu(
        self, api: Callable[..., Any], restaurant: Restaurant, menu: Menu, category: MenuCategory
    ) -> None:
        other_menu = MenuFactory(restaurant=restaurant, name="Lunch")
        foreign = MenuCategoryFactory(menu=other_menu, name="Soups", sort_order=1)
        item = MenuItemFactory(menu=menu, category=category, restaurant=restaurant)
        client = self._admin(api, restaurant)

        response: Any = client.post(
            reverse("admin-menu-item-bulk"),
            {"ids": [str(item.public_id)], "action": "set_category", "category": str(foreign.public_id)},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        item.refresh_from_db()
        assert item.category_id == category.id

    def test_delete_removes_many_items(
        self, api: Callable[..., Any], restaurant: Restaurant, menu: Menu, category: MenuCategory
    ) -> None:
        a = MenuItemFactory(menu=menu, category=category, restaurant=restaurant)
        b = MenuItemFactory(menu=menu, category=category, restaurant=restaurant)
        client = self._admin(api, restaurant)

        response: Any = client.post(
            reverse("admin-menu-item-bulk"),
            {"ids": [str(a.public_id), str(b.public_id)], "action": "delete"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert MenuItem.objects.filter(public_id__in=[a.public_id, b.public_id]).count() == 0

    def test_does_not_touch_other_restaurants_items(
        self,
        api: Callable[..., Any],
        restaurant: Restaurant,
        empty_restaurant: Restaurant,
        menu: Menu,
        category: MenuCategory,
    ) -> None:
        other_menu = MenuFactory(restaurant=empty_restaurant, name="Other")
        foreign = MenuItemFactory(menu=other_menu, restaurant=empty_restaurant, is_available=True)
        client = self._admin(api, restaurant)

        response: Any = client.post(
            reverse("admin-menu-item-bulk"),
            {"ids": [str(foreign.public_id)], "action": "set_available", "is_available": False},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"updated": 0}
        foreign.refresh_from_db()
        assert foreign.is_available is True

    def test_requires_admin_role(
        self, api: Callable[..., Any], restaurant: Restaurant, menu: Menu, category: MenuCategory
    ) -> None:
        item = MenuItemFactory(menu=menu, category=category, restaurant=restaurant)
        waiter = api(role=RoleCode.WAITER, restaurant_id=restaurant.id).client

        response: Any = waiter.post(
            reverse("admin-menu-item-bulk"),
            {"ids": [str(item.public_id)], "action": "delete"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
