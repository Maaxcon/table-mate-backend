from collections.abc import Callable
from typing import Any

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.authentication.models import RoleCode

ENDPOINTS = {
    "editor:layout-list": "layout-list",
    "reservations:reservation-list": "reservation-list",
    "restaurants:restaurant-list": "restaurant-list",
    "restaurants:settings-list": "restaurant-settings-list",
    "restaurants:table-list": "table-list",
    "orders:session-list": "session-list",
    "orders:order-list": "order-list",
    "orders:ticket-list": "ticket-list",
    "orders:order-item-list": "order-item-list",
    "payments:payment-list": "payment-list",
}

PUBLIC_ENDPOINTS = {
    "menu:menu-list": "menu-list",
    "menu:category-list": "menu-category-list",
    "menu:item-list": "menu-item-list",
}

ROLE_ALLOW_MATRIX: dict[str, set[str]] = {
    "editor:layout-list": {RoleCode.ADMIN, RoleCode.WAITER},
    "reservations:reservation-list": {RoleCode.ADMIN, RoleCode.WAITER, RoleCode.CUSTOMER},
    "restaurants:restaurant-list": {RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK},
    "restaurants:settings-list": {RoleCode.ADMIN},
    "restaurants:table-list": {RoleCode.ADMIN, RoleCode.WAITER},
    "orders:session-list": {RoleCode.ADMIN, RoleCode.WAITER},
    "orders:order-list": {RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK},
    "orders:ticket-list": {RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK},
    "orders:order-item-list": {RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK},
    "payments:payment-list": {RoleCode.ADMIN},
}

ROLES = [RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK, RoleCode.CUSTOMER]


@pytest.mark.django_db
@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("ep_name,url_name", list(ENDPOINTS.items()), ids=list(ENDPOINTS.keys()))
def test_protected_endpoint_role_enforcement(ep_name: str, url_name: str, role: str, api: Callable[..., Any]) -> None:
    ctx = api(role=role)
    response = ctx.client.get(reverse(url_name))
    if role in ROLE_ALLOW_MATRIX[ep_name]:
        assert response.status_code == status.HTTP_200_OK, f"{role} should be allowed on {ep_name}"
    else:
        assert response.status_code == status.HTTP_403_FORBIDDEN, f"{role} should be denied on {ep_name}"
        assert "detail" in response.data
        assert isinstance(response.data["detail"], str)


@pytest.mark.django_db
@pytest.mark.parametrize("ep_name,url_name", list(PUBLIC_ENDPOINTS.items()), ids=list(PUBLIC_ENDPOINTS.keys()))
def test_public_menu_endpoints_allow_anonymous(ep_name: str, url_name: str, restaurant: Any) -> None:
    client = APIClient()
    url = f"{reverse(url_name)}?restaurant={restaurant.public_id}"
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK, f"{ep_name} should return 200 with valid restaurant"


@pytest.mark.django_db
@pytest.mark.parametrize("ep_name,url_name", list(ENDPOINTS.items()), ids=list(ENDPOINTS.keys()))
def test_protected_endpoints_reject_anonymous(ep_name: str, url_name: str) -> None:
    client = APIClient()
    response = client.get(reverse(url_name))
    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    ), f"{ep_name} should reject anonymous users"
