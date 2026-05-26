from decimal import Decimal

import factory
import pytest
from django.test import Client
from faker import Faker as FakerProxy

from apps.menu.models import Menu, MenuCategory, MenuItem
from apps.restaurants.models import Restaurant

fake = FakerProxy()


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
