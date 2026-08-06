from collections.abc import Callable

import pytest

from apps.authentication.models import RoleCode, User
from apps.restaurants.models import Restaurant
from tests.conftest import AuthContext, UserFactory


@pytest.mark.django_db
class TestEmployeeRemove:
    url = "/api/restaurants/employees/{employee_id}/"

    def test_demotes_staff_to_customer_and_preserves_account(
        self, api_factory: Callable[[User, int], AuthContext]
    ) -> None:
        restaurant = Restaurant.objects.create(name="Test Restaurant")
        admin = UserFactory.create(role=RoleCode.ADMIN, restaurant=restaurant)
        employee = UserFactory.create(role=RoleCode.WAITER, restaurant=restaurant)
        token_version = employee.token_version

        response = api_factory(admin, restaurant.id).client.delete(self.url.format(employee_id=employee.public_id))

        assert response.status_code == 204
        employee.refresh_from_db()
        assert employee.role == RoleCode.CUSTOMER
        assert employee.restaurant_id is None
        assert employee.is_active is True
        assert employee.token_version == token_version + 1
        assert User.objects.filter(pk=employee.pk).exists()

    def test_rejects_removing_last_active_admin(self, api_factory: Callable[[User, int], AuthContext]) -> None:
        restaurant = Restaurant.objects.create(name="Test Restaurant")
        admin = UserFactory.create(role=RoleCode.ADMIN, restaurant=restaurant)

        response = api_factory(admin, restaurant.id).client.delete(self.url.format(employee_id=admin.public_id))

        assert response.status_code == 400
        assert response.data == ["You cannot demote or deactivate the last active admin."]
        admin.refresh_from_db()
        assert admin.role == RoleCode.ADMIN
        assert admin.restaurant_id == restaurant.id

    def test_allows_removing_admin_when_another_active_admin_exists(
        self, api_factory: Callable[[User, int], AuthContext]
    ) -> None:
        restaurant = Restaurant.objects.create(name="Test Restaurant")
        admin = UserFactory.create(role=RoleCode.ADMIN, restaurant=restaurant)
        UserFactory.create(role=RoleCode.ADMIN, restaurant=restaurant)

        response = api_factory(admin, restaurant.id).client.delete(self.url.format(employee_id=admin.public_id))

        assert response.status_code == 204
        admin.refresh_from_db()
        assert admin.role == RoleCode.CUSTOMER
        assert admin.restaurant_id is None

    def test_rejects_non_admin(self, api_factory: Callable[[User, int], AuthContext]) -> None:
        restaurant = Restaurant.objects.create(name="Test Restaurant")
        waiter = UserFactory.create(role=RoleCode.WAITER, restaurant=restaurant)
        employee = UserFactory.create(role=RoleCode.COOK, restaurant=restaurant)

        response = api_factory(waiter, restaurant.id).client.delete(self.url.format(employee_id=employee.public_id))

        assert response.status_code == 403
        employee.refresh_from_db()
        assert employee.role == RoleCode.COOK
        assert employee.restaurant_id == restaurant.id

    def test_rejects_employee_from_another_restaurant(self, api_factory: Callable[[User, int], AuthContext]) -> None:
        restaurant = Restaurant.objects.create(name="Test Restaurant")
        other_restaurant = Restaurant.objects.create(name="Other Restaurant")
        admin = UserFactory.create(role=RoleCode.ADMIN, restaurant=restaurant)
        employee = UserFactory.create(role=RoleCode.COOK, restaurant=other_restaurant)

        response = api_factory(admin, restaurant.id).client.delete(self.url.format(employee_id=employee.public_id))

        assert response.status_code == 404
        employee.refresh_from_db()
        assert employee.role == RoleCode.COOK
        assert employee.restaurant_id == other_restaurant.id
