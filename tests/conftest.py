from collections.abc import Callable
from decimal import Decimal
from typing import Any

import factory
import pytest
from django.test import Client
from faker import Faker as FakerProxy
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.models import RoleCode, User
from apps.menu.models import Menu, MenuCategory, MenuItem
from apps.restaurants.models import Restaurant

fake = FakerProxy()


class UserFactory(factory.django.DjangoModelFactory):  # type: ignore[misc]
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    role = RoleCode.CUSTOMER
    is_active = True


class RestaurantFactory(factory.django.DjangoModelFactory):  # type: ignore[misc]
    class Meta:
        model = Restaurant

    name = factory.Sequence(lambda n: f"Restaurant {n}")
    address = "123 Main St"


class MenuFactory(factory.django.DjangoModelFactory):  # type: ignore[misc]
    class Meta:
        model = Menu

    restaurant = factory.SubFactory(RestaurantFactory)
    name = factory.Sequence(lambda n: f"Menu {n}")
    is_active = True


class MenuCategoryFactory(factory.django.DjangoModelFactory):  # type: ignore[misc]
    class Meta:
        model = MenuCategory

    menu = factory.SubFactory(MenuFactory)
    name = factory.Sequence(lambda n: f"Category {n}")
    sort_order = factory.Sequence(lambda n: n)


class MenuItemFactory(factory.django.DjangoModelFactory):  # type: ignore[misc]
    class Meta:
        model = MenuItem

    restaurant = factory.SelfAttribute("menu.restaurant")
    menu = factory.SubFactory(MenuFactory)
    category = factory.SubFactory(MenuCategoryFactory, menu=factory.SelfAttribute("..menu"))
    name = factory.Sequence(lambda n: f"Item {n}")
    description = factory.Faker("sentence")
    price = Decimal("29.9900")
    sort_order = factory.Sequence(lambda n: n)
    is_available = True


@pytest.fixture
def api() -> Callable[..., Any]:
    def _api(role: str) -> Any:
        user: Any = UserFactory(role=role)
        refresh = RefreshToken.for_user(user)
        refresh["role"] = user.role
        refresh["token_version"] = user.token_version
        access_token = str(refresh.access_token)
        client = Client(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        return type("ApiCtx", (), {"client": client})()

    return _api


@pytest.fixture
def user_factory() -> UserFactory:
    return UserFactory.build


@pytest.fixture
def api_client() -> Client:
    return Client()


@pytest.fixture
def restaurant() -> Restaurant:
    return RestaurantFactory()


@pytest.fixture
def menu(restaurant: Restaurant) -> Menu:
    return MenuFactory(restaurant=restaurant, name="Dinner")


@pytest.fixture
def category(menu: Menu) -> MenuCategory:
    return MenuCategoryFactory(menu=menu, name="Mains", sort_order=1)


@pytest.fixture
def empty_restaurant() -> Restaurant:
    return RestaurantFactory(name="Empty Restaurant")


@pytest.fixture
def item(menu: Menu, category: MenuCategory, restaurant: Restaurant) -> MenuItem:
    return MenuItemFactory(
        menu=menu,
        category=category,
        restaurant=restaurant,
        name="Steak",
        description="Grilled to perfection",
        sort_order=1,
    )
