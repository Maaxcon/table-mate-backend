from collections.abc import Callable
from typing import Any

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.authentication.models import RoleCode
from apps.authentication.services import issue_tokens_with_restaurant
from tests.conftest import UserFactory

ENDPOINTS: list[str] = [
    "layout-list",
    "reservation-list",
    "restaurant-list",
    "restaurant-settings-list",
    "table-list",
    "session-list",
    "order-list",
    "ticket-list",
    "order-item-list",
    "payment-list",
]

PUBLIC_ENDPOINTS: list[str] = [
    "menu-list",
    "menu-category-list",
    "menu-item-list",
]

ROLE_ALLOW_MATRIX: dict[str, set[str]] = {
    "layout-list": {RoleCode.ADMIN, RoleCode.WAITER},
    "reservation-list": {RoleCode.ADMIN, RoleCode.WAITER, RoleCode.CUSTOMER},
    "restaurant-list": {RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK},
    "restaurant-settings-list": {RoleCode.ADMIN},
    "table-list": {RoleCode.ADMIN, RoleCode.WAITER},
    "session-list": {RoleCode.ADMIN, RoleCode.WAITER},
    "order-list": {RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK},
    "ticket-list": {RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK},
    "order-item-list": {RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK},
    "payment-list": {RoleCode.ADMIN},
}

ROLES = [RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK, RoleCode.CUSTOMER]


@pytest.mark.django_db
@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("url_name", ENDPOINTS)
def test_protected_endpoint_role_enforcement(
    url_name: str, role: str, api: Callable[..., Any], restaurant: Any
) -> None:
    ctx = api(role=role, restaurant_id=restaurant.id)
    response = ctx.client.get(reverse(url_name))
    if role in ROLE_ALLOW_MATRIX[url_name]:
        assert response.status_code == status.HTTP_200_OK, f"{role} should be allowed on {url_name}"
    else:
        assert response.status_code == status.HTTP_403_FORBIDDEN, f"{role} should be denied on {url_name}"
        assert response.data == {
            "detail": "You do not have permission to perform this action.",
            "code": "permission_denied",
        }


@pytest.mark.django_db
@pytest.mark.parametrize("url_name", PUBLIC_ENDPOINTS)
def test_public_menu_endpoints_allow_anonymous(url_name: str, restaurant: Any) -> None:
    client = APIClient()
    url = f"{reverse(url_name)}?restaurant={restaurant.public_id}"
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK, f"{url_name} should return 200 with valid restaurant"


@pytest.mark.django_db
@pytest.mark.parametrize("url_name", ENDPOINTS)
def test_protected_endpoints_reject_anonymous(url_name: str) -> None:
    client = APIClient()
    response = client.get(reverse(url_name))
    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    ), f"{url_name} should reject anonymous users"


@pytest.mark.django_db
def test_role_change_invalidates_existing_token(restaurant: Any) -> None:
    user = UserFactory.create(role=RoleCode.ADMIN, restaurant=restaurant)
    access, _ = issue_tokens_with_restaurant(user, restaurant.id)  # type: ignore[arg-type]
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    response = client.get(reverse("layout-list"))
    assert response.status_code == status.HTTP_200_OK

    user.role = RoleCode.CUSTOMER  # type: ignore[attr-defined]
    user.save()
    user.refresh_from_db()
    assert user.token_version == 1  # type: ignore[attr-defined]

    response = client.get(reverse("layout-list"))
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
