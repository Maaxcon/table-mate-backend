from collections.abc import Callable
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.authentication.models import RoleCode
from apps.restaurants.models import Restaurant, Table, TableStatus

User = get_user_model()


@pytest.fixture
def restaurant() -> Restaurant:
    return Restaurant.objects.create(name="Test Restaurant", address="123 Main St")


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
def customer_user() -> Any:
    return User.objects.create_user(
        email="customer@example.com",
        password="password",
        role=RoleCode.CUSTOMER,
    )


@pytest.fixture
def api_factory() -> Callable[..., APIClient]:
    def _factory(user: Any, restaurant_id: int) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=user, token={"restaurant_id": str(restaurant_id)})  # type: ignore[arg-type]
        return client

    return _factory
