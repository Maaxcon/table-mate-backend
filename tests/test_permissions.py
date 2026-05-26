from typing import Any

import pytest
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APIRequestFactory

from apps.authentication.models import RoleCode
from apps.authentication.permissions import (
    IsAdmin,
    IsCustomer,
    IsFloor,
    IsFloorOrCustomer,
    IsKitchen,
    IsStaff,
)

PERM_CLASSES: dict[type[Any], frozenset[str]] = {
    IsAdmin: frozenset({RoleCode.ADMIN}),
    IsStaff: frozenset({RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK}),
    IsFloor: frozenset({RoleCode.ADMIN, RoleCode.WAITER}),
    IsKitchen: frozenset({RoleCode.ADMIN, RoleCode.COOK}),
    IsCustomer: frozenset({RoleCode.CUSTOMER}),
    IsFloorOrCustomer: frozenset({RoleCode.ADMIN, RoleCode.WAITER, RoleCode.CUSTOMER}),
}

ROLES: list[str] = [RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK, RoleCode.CUSTOMER]


@pytest.mark.parametrize("user_role", ROLES)
@pytest.mark.parametrize("perm_cls", PERM_CLASSES)
def test_role_permission_matrix(perm_cls: type[Any], user_role: str, user_factory: Any) -> None:
    request = APIRequestFactory().get("/")
    request.user = user_factory(role=user_role)
    expected = user_role in PERM_CLASSES[perm_cls]
    assert perm_cls().has_permission(request, None) is expected


@pytest.mark.parametrize("perm_cls", PERM_CLASSES)
def test_denied_for_anonymous(perm_cls: type[Any]) -> None:
    request = APIRequestFactory().get("/")
    request.user = AnonymousUser()
    assert perm_cls().has_permission(request, None) is False


@pytest.mark.parametrize("perm_cls", PERM_CLASSES)
def test_denied_when_user_is_none(perm_cls: type[Any]) -> None:
    request = APIRequestFactory().get("/")
    request.user = None  # type: ignore[assignment]
    assert perm_cls().has_permission(request, None) is False
