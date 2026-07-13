# mypy: disable-error-code="no-untyped-call"
from collections.abc import Callable
from typing import Any, cast

import pytest
from django.urls import reverse

from apps.authentication.models import RoleCode
from apps.restaurants.models import Restaurant, Table
from tests.conftest import AuthContext, RestaurantFactory


def _qr_url(table: Table) -> str:
    return reverse("table-qr", kwargs={"public_id": table.public_id})


@pytest.mark.django_db
def test_qr_returns_png_for_own_restaurant_admin(
    api: Callable[..., AuthContext], restaurant: Restaurant, table: Table
) -> None:
    ctx = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)

    response = ctx.client.get(_qr_url(table))

    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")


@pytest.mark.django_db
def test_qr_requires_authentication(api_client: Any, table: Table) -> None:
    response = api_client.get(_qr_url(table))
    assert response.status_code == 401


@pytest.mark.parametrize("role", [RoleCode.WAITER, RoleCode.COOK, RoleCode.CUSTOMER])
@pytest.mark.django_db
def test_qr_denied_for_non_admin_roles(
    api: Callable[..., AuthContext], restaurant: Restaurant, table: Table, role: str
) -> None:
    ctx = api(role=role, restaurant_id=restaurant.id)

    response = ctx.client.get(_qr_url(table))

    assert response.status_code == 403


@pytest.mark.django_db
def test_qr_not_found_for_other_restaurants_admin(api: Callable[..., AuthContext], table: Table) -> None:
    other_restaurant = cast(Restaurant, RestaurantFactory(name="Other Restaurant"))
    ctx = api(role=RoleCode.ADMIN, restaurant_id=other_restaurant.id)

    response = ctx.client.get(_qr_url(table))

    assert response.status_code == 404
