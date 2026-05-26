from collections.abc import Callable
from typing import Any

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.authentication.models import RoleCode

ENDPOINTS = {
    "editor:layout-list": "/api/editor/layouts/",
    "reservations:reservation-list": "/api/reservations/reservations/",
    "restaurants:restaurant-list": "/api/restaurants/restaurants/",
    "restaurants:settings-list": "/api/restaurants/restaurant-settings/",
    "restaurants:table-list": "/api/restaurants/tables/",
    "orders:session-list": "/api/orders/sessions/",
    "orders:order-list": "/api/orders/orders/",
    "orders:ticket-list": "/api/orders/tickets/",
    "orders:order-item-list": "/api/orders/order-items/",
}

PUBLIC_ENDPOINTS = {
    "menu:menu-list": "/api/menu/menus/",
    "menu:category-list": "/api/menu/menu-categories/",
    "menu:item-list": "/api/menu/menu-items/",
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
}

ROLES = [RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK, RoleCode.CUSTOMER]


@pytest.mark.django_db
@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("ep_name,ep_path", list(ENDPOINTS.items()), ids=list(ENDPOINTS.keys()))
def test_protected_endpoint_role_enforcement(ep_name: str, ep_path: str, role: str, api: Callable[..., Any]) -> None:
    ctx = api(role=role)
    response = ctx.client.get(ep_path)
    if role in ROLE_ALLOW_MATRIX[ep_name]:
        assert response.status_code != status.HTTP_403_FORBIDDEN, f"{role} should be allowed on {ep_name}"
    else:
        assert response.status_code == status.HTTP_403_FORBIDDEN, f"{role} should be denied on {ep_name}"
        assert "detail" in response.data
        assert isinstance(response.data["detail"], str)


@pytest.mark.django_db
@pytest.mark.parametrize("ep_name,ep_path", list(PUBLIC_ENDPOINTS.items()), ids=list(PUBLIC_ENDPOINTS.keys()))
def test_public_menu_endpoints_allow_anonymous(ep_name: str, ep_path: str) -> None:
    client = APIClient()
    response = client.get(ep_path)
    assert response.status_code != status.HTTP_403_FORBIDDEN, f"{ep_name} should be accessible without auth"
    assert response.status_code != status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
@pytest.mark.parametrize("ep_name,ep_path", list(ENDPOINTS.items()), ids=list(ENDPOINTS.keys()))
def test_protected_endpoints_reject_anonymous(ep_name: str, ep_path: str) -> None:
    client = APIClient()
    response = client.get(ep_path)
    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    ), f"{ep_name} should reject anonymous users"
