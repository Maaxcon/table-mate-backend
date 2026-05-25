import pytest

from apps.authentication.models import RoleCode
from apps.restaurants.models import Restaurant
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

    def test_restaurant_change_increments_token_version(self) -> None:
        restaurant_a = Restaurant.objects.create(name="A")
        restaurant_b = Restaurant.objects.create(name="B")
        user = UserFactory.create(role=RoleCode.WAITER, restaurant=restaurant_a)
        assert user.token_version == 0

        user.restaurant = restaurant_b
        user.save()
        user.refresh_from_db()

        assert user.token_version == 1

    def test_restaurant_unassigned_increments_token_version(self) -> None:
        restaurant = Restaurant.objects.create(name="A")
        user = UserFactory.create(role=RoleCode.WAITER, restaurant=restaurant)
        assert user.token_version == 0

        user.restaurant = None
        user.save()
        user.refresh_from_db()

        assert user.token_version == 1

    def test_unrelated_field_change_does_not_increment_token_version(self) -> None:
        user = UserFactory.create(role=RoleCode.CUSTOMER)
        user.first_name = "Changed"
        user.save()
        user.refresh_from_db()

        assert user.token_version == 0
