# mypy: disable-error-code="no-untyped-call"
from collections.abc import Callable
from decimal import Decimal
from typing import TYPE_CHECKING, Any, NamedTuple, cast

import pytest
from django.test import Client
from factory.declarations import (
    PostGenerationMethodCall,
    SelfAttribute,
    Sequence,
    SubFactory,
)
from factory.django import DjangoModelFactory
from factory.faker import Faker
from rest_framework.test import APIClient

from apps.authentication.models import RoleCode
from apps.menu.models import Menu, MenuCategory, MenuItem
from apps.restaurants.models import Restaurant, Table, TableStatus

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

    User = AbstractUser
else:
    from django.contrib.auth import get_user_model

    User = get_user_model()


class UserFactory(DjangoModelFactory[User]):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = Sequence(lambda n: f"user{n}@example.com")
    password = PostGenerationMethodCall("set_password", "password")
    role = RoleCode.CUSTOMER
    first_name = Faker("first_name")
    last_name = Faker("last_name")
    is_active = True


class RestaurantFactory(DjangoModelFactory[Restaurant]):
    class Meta:
        model = Restaurant

    name = Sequence(lambda n: f"Restaurant {n}")
    address = "123 Main St"


class MenuFactory(DjangoModelFactory[Menu]):
    class Meta:
        model = Menu

    restaurant = SubFactory(RestaurantFactory)
    name = Sequence(lambda n: f"Menu {n}")
    is_active = True


class MenuCategoryFactory(DjangoModelFactory[MenuCategory]):
    class Meta:
        model = MenuCategory

    menu = SubFactory(MenuFactory)
    name = Sequence(lambda n: f"Category {n}")
    sort_order = Sequence(lambda n: n)


class MenuItemFactory(DjangoModelFactory[MenuItem]):
    class Meta:
        model = MenuItem

    restaurant = SelfAttribute("menu.restaurant")
    menu = SubFactory(MenuFactory)
    category = SubFactory(MenuCategoryFactory, menu=SelfAttribute("..menu"))
    name = Sequence(lambda n: f"Item {n}")
    description = Faker("sentence")
    price = Decimal("29.9900")
    sort_order = Sequence(lambda n: n)
    is_available = True


@pytest.fixture
def user_factory() -> Callable[..., Any]:
    def _factory(role: str = RoleCode.CUSTOMER, **kwargs: Any) -> Any:
        return UserFactory.build(role=role, **kwargs)

    return _factory


class AuthContext(NamedTuple):
    client: APIClient
    user: Any


@pytest.fixture
def api(user_factory: Callable[..., Any]) -> Callable[..., AuthContext]:
    def _api(role: str = RoleCode.CUSTOMER, **kwargs: Any) -> AuthContext:
        user = user_factory(role=role, **kwargs)
        client = APIClient()
        client.force_authenticate(user=user)

        return AuthContext(client=client, user=user)

    return _api


@pytest.fixture
def api_factory() -> Callable[..., AuthContext]:
    def _factory(user: Any, restaurant_id: int) -> AuthContext:
        client = APIClient()
        client.force_authenticate(user=user, token={"restaurant_id": str(restaurant_id)})  # type: ignore[arg-type]

        return AuthContext(client=client, user=user)

    return _factory


@pytest.fixture
def api_client() -> Client:
    return Client()


@pytest.fixture
def restaurant() -> Restaurant:
    return cast(Restaurant, RestaurantFactory(name="Test Restaurant", address="123 Main St"))


@pytest.fixture
def empty_restaurant() -> Restaurant:
    return cast(Restaurant, RestaurantFactory(name="Empty Restaurant"))


@pytest.fixture
def table(restaurant: Restaurant) -> Table:
    return Table.objects.create(
        restaurant=restaurant,
        table_number="T1",
        capacity=4,
        active=True,
        status=TableStatus.FREE,
    )


@pytest.fixture
def menu(restaurant: Restaurant) -> Menu:
    return cast(Menu, MenuFactory(restaurant=restaurant, name="Dinner"))


@pytest.fixture
def category(menu: Menu) -> MenuCategory:
    return cast(MenuCategory, MenuCategoryFactory(menu=menu, name="Mains", sort_order=1))


@pytest.fixture
def item(menu: Menu, category: MenuCategory, restaurant: Restaurant) -> MenuItem:
    return cast(
        MenuItem,
        MenuItemFactory(
            menu=menu,
            category=category,
            restaurant=restaurant,
            name="Steak",
            description="Grilled to perfection",
            sort_order=1,
        ),
    )
