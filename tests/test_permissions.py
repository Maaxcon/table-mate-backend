from typing import Any
from unittest.mock import MagicMock

import pytest
from django.http import HttpRequest
from rest_framework.test import APIRequestFactory

from apps.authentication.models import RoleCode
from apps.authentication.permissions import IsAdmin, IsCustomer, IsFloor, IsKitchen


@pytest.fixture
def dummy_view() -> Any:
    return MagicMock()


def _build_request(user_mock: MagicMock) -> HttpRequest:
    request = APIRequestFactory().get("/")
    request.user = user_mock
    return request


def _mock_user(role: str | None = None, is_authenticated: bool = True) -> Any:
    user = MagicMock()
    user.role = role
    user.is_authenticated = is_authenticated
    return user


def _assert_granted(perm: Any, request: HttpRequest, view: Any) -> None:
    assert perm.has_permission(request, view) is True


def _assert_denied(perm: Any, request: HttpRequest, view: Any) -> None:
    assert perm.has_permission(request, view) is False


class TestIsAdmin:
    def test_granted_for_admin(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.ADMIN)
        _assert_granted(IsAdmin(), _build_request(user), dummy_view)

    def test_denied_for_waiter(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.WAITER)
        _assert_denied(IsAdmin(), _build_request(user), dummy_view)

    def test_denied_for_cook(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.COOK)
        _assert_denied(IsAdmin(), _build_request(user), dummy_view)

    def test_denied_for_customer(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.CUSTOMER)
        _assert_denied(IsAdmin(), _build_request(user), dummy_view)

    def test_denied_for_unauthenticated(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.CUSTOMER, is_authenticated=False)
        _assert_denied(IsAdmin(), _build_request(user), dummy_view)

    def test_denied_when_user_is_none(self, dummy_view: Any) -> None:
        request = APIRequestFactory().get("/")
        request.user = None  # type: ignore[assignment]
        _assert_denied(IsAdmin(), request, dummy_view)


class TestIsFloor:
    def test_granted_for_admin(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.ADMIN)
        _assert_granted(IsFloor(), _build_request(user), dummy_view)

    def test_granted_for_waiter(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.WAITER)
        _assert_granted(IsFloor(), _build_request(user), dummy_view)

    def test_denied_for_cook(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.COOK)
        _assert_denied(IsFloor(), _build_request(user), dummy_view)

    def test_denied_for_customer(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.CUSTOMER)
        _assert_denied(IsFloor(), _build_request(user), dummy_view)

    def test_denied_for_unauthenticated(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.CUSTOMER, is_authenticated=False)
        _assert_denied(IsFloor(), _build_request(user), dummy_view)

    def test_denied_when_user_is_none(self, dummy_view: Any) -> None:
        request = APIRequestFactory().get("/")
        request.user = None  # type: ignore[assignment]
        _assert_denied(IsFloor(), request, dummy_view)


class TestIsKitchen:
    def test_granted_for_admin(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.ADMIN)
        _assert_granted(IsKitchen(), _build_request(user), dummy_view)

    def test_granted_for_cook(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.COOK)
        _assert_granted(IsKitchen(), _build_request(user), dummy_view)

    def test_denied_for_waiter(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.WAITER)
        _assert_denied(IsKitchen(), _build_request(user), dummy_view)

    def test_denied_for_customer(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.CUSTOMER)
        _assert_denied(IsKitchen(), _build_request(user), dummy_view)

    def test_denied_for_unauthenticated(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.CUSTOMER, is_authenticated=False)
        _assert_denied(IsKitchen(), _build_request(user), dummy_view)

    def test_denied_when_user_is_none(self, dummy_view: Any) -> None:
        request = APIRequestFactory().get("/")
        request.user = None  # type: ignore[assignment]
        _assert_denied(IsKitchen(), request, dummy_view)


class TestIsCustomer:
    def test_granted_for_customer(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.CUSTOMER)
        _assert_granted(IsCustomer(), _build_request(user), dummy_view)

    def test_denied_for_admin(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.ADMIN)
        _assert_denied(IsCustomer(), _build_request(user), dummy_view)

    def test_denied_for_waiter(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.WAITER)
        _assert_denied(IsCustomer(), _build_request(user), dummy_view)

    def test_denied_for_cook(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.COOK)
        _assert_denied(IsCustomer(), _build_request(user), dummy_view)

    def test_denied_for_unauthenticated(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.CUSTOMER, is_authenticated=False)
        _assert_denied(IsCustomer(), _build_request(user), dummy_view)

    def test_denied_when_user_is_none(self, dummy_view: Any) -> None:
        request = APIRequestFactory().get("/")
        request.user = None  # type: ignore[assignment]
        _assert_denied(IsCustomer(), request, dummy_view)
