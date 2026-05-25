import pytest

from apps.authentication.models import RoleCode
from tests.conftest import UserFactory


@pytest.mark.django_db
class TestInvalidateTokensOnRoleChange:
    def test_role_change_increments_token_version(self) -> None:
        user = UserFactory.create(role=RoleCode.CUSTOMER)
        assert user.token_version == 0

        user.role = RoleCode.WAITER
        user.save()
        user.refresh_from_db()

        assert user.token_version == 1

    def test_same_role_does_not_increment_token_version(self) -> None:
        user = UserFactory.create(role=RoleCode.CUSTOMER)
        user.first_name = "Updated"
        user.save()
        user.refresh_from_db()

        assert user.token_version == 0

    def test_multiple_role_changes_increment_each_time(self) -> None:
        user = UserFactory.create(role=RoleCode.CUSTOMER)

        user.role = RoleCode.WAITER
        user.save()
        user.role = RoleCode.COOK
        user.save()
        user.refresh_from_db()

        assert user.token_version == 2

    def test_new_user_starts_at_zero(self) -> None:
        user = UserFactory.create()
        assert user.token_version == 0
