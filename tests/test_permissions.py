from typing import Any
from unittest.mock import MagicMock

import pytest
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.authentication.models import RoleCode
from apps.authentication.permissions import IsAdmin, IsCook, IsCustomer, IsWaiter


@pytest.fixture
def dummy_view() -> Any:
    return MagicMock()


def _build_request(user_mock: MagicMock) -> Request:
    request = APIRequestFactory().get("/")
    request.user = user_mock
    return request


def _mock_user(role: str | None = None, is_authenticated: bool = True) -> Any:
    user = MagicMock()
    user.role = role
    user.is_authenticated = is_authenticated
    return user


def _assert_granted(perm: Any, request: Request, view: Any) -> None:
    assert perm.has_permission(request, view) is True


def _assert_denied(perm: Any, request: Request, view: Any) -> None:
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


class TestIsWaiter:
    def test_granted_for_waiter(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.WAITER)
        _assert_granted(IsWaiter(), _build_request(user), dummy_view)

    def test_denied_for_admin(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.ADMIN)
        _assert_denied(IsWaiter(), _build_request(user), dummy_view)

    def test_denied_for_cook(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.COOK)
        _assert_denied(IsWaiter(), _build_request(user), dummy_view)

    def test_denied_for_customer(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.CUSTOMER)
        _assert_denied(IsWaiter(), _build_request(user), dummy_view)

    def test_denied_for_unauthenticated(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.CUSTOMER, is_authenticated=False)
        _assert_denied(IsWaiter(), _build_request(user), dummy_view)


class TestIsCook:
    def test_granted_for_cook(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.COOK)
        _assert_granted(IsCook(), _build_request(user), dummy_view)

    def test_denied_for_admin(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.ADMIN)
        _assert_denied(IsCook(), _build_request(user), dummy_view)

    def test_denied_for_waiter(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.WAITER)
        _assert_denied(IsCook(), _build_request(user), dummy_view)

    def test_denied_for_customer(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.CUSTOMER)
        _assert_denied(IsCook(), _build_request(user), dummy_view)

    def test_denied_for_unauthenticated(self, dummy_view: Any) -> None:
        user = _mock_user(role=RoleCode.CUSTOMER, is_authenticated=False)
        _assert_denied(IsCook(), _build_request(user), dummy_view)


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
