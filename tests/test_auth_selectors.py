import pytest

from apps.authentication.selectors import get_user_by_email
from tests.conftest import UserFactory


@pytest.mark.django_db
class TestGetUserByEmail:
    def test_returns_user_when_found(self) -> None:
        user = UserFactory.create(email="find@example.com")
        assert get_user_by_email("find@example.com") == user

    def test_returns_none_when_not_found(self) -> None:
        assert get_user_by_email("nobody@example.com") is None

    def test_case_sensitive(self) -> None:
        UserFactory.create(email="lower@example.com")
        assert get_user_by_email("LOWER@example.com") is None
