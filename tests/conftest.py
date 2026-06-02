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
from apps.authentication.services import issue_tokens_with_restaurant
from apps.menu.models import Menu, MenuCategory, MenuItem
from apps.restaurants.models import Restaurant, RestaurantSettings, Table, TableStatus

if TYPE_CHECKING:
    from apps.authentication.models import User as _User

    User = _User
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


class RestaurantSettingsFactory(DjangoModelFactory[RestaurantSettings]):
    class Meta:
        model = RestaurantSettings

    restaurant = SubFactory(RestaurantFactory)
    timezone = "Europe/Kyiv"
    currency = "UAH"
    locale = "uk"
    default_tax_rate = Decimal("0.1000")
    default_service_charge = Decimal("0.0500")
    working_hours = {
        "mon": {"open": "09:00", "close": "22:00"},
        "tue": {"open": "09:00", "close": "22:00"},
        "wed": {"open": "09:00", "close": "22:00"},
        "thu": {"open": "09:00", "close": "22:00"},
        "fri": {"open": "09:00", "close": "23:00"},
        "sat": {"open": "10:00", "close": "23:00"},
        "sun": {"open": "10:00", "close": "21:00"},
    }
    eta_min_minutes = 20
    eta_max_minutes = 30
    price_band = 2


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


@pytest.fixture(autouse=True)
def _clear_cache() -> Any:
    # Reset rate-limit (throttle) counters between tests so they don't leak.
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


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
    def _api(role: str = RoleCode.CUSTOMER, restaurant_id: int | None = None, **kwargs: Any) -> AuthContext:
        user = user_factory(role=role, **kwargs)
        user.save()  # user_factory uses build() — persist before issuing JWT
        client = APIClient()
        if restaurant_id is not None:
            access, _ = issue_tokens_with_restaurant(user, restaurant_id)
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        else:
            client.force_authenticate(user=user)

        return AuthContext(client=client, user=user)

    return _api


@pytest.fixture
def api_factory() -> Callable[..., AuthContext]:
    def _factory(user: Any, restaurant_id: int) -> AuthContext:
        client = APIClient()
        access, _ = issue_tokens_with_restaurant(user, restaurant_id)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

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


@pytest.fixture
def restaurant_settings(restaurant: Restaurant) -> RestaurantSettings:
    return RestaurantSettingsFactory(restaurant=restaurant)
