from collections.abc import Callable

import pytest

from apps.authentication.models import RoleCode, User
from apps.restaurants.models import Restaurant
from tests.conftest import AuthContext, UserFactory


@pytest.mark.django_db
class TestEmployeeAssign:
    url = "/api/restaurants/employees/assign/"
    unavailable_user_message = "This user cannot be assigned as staff."

    def test_assigns_customer_to_admin_restaurant(self, api_factory: Callable[[User, int], AuthContext]) -> None:
        restaurant = Restaurant.objects.create(name="Test Restaurant")
        admin = UserFactory.create(role=RoleCode.ADMIN, restaurant=restaurant)
        customer = UserFactory.create(
            role=RoleCode.CUSTOMER,
            first_name="Existing",
            last_name="Customer",
            phone="+380000000000",
            is_active=False,
        )

        response = api_factory(admin, restaurant.id).client.post(
            self.url,
            {"email": customer.email, "role": RoleCode.WAITER},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["role"] == RoleCode.WAITER
        customer.refresh_from_db()
        assert customer.restaurant_id == restaurant.id
        assert customer.is_active is False
        assert customer.first_name == "Existing"
        assert customer.last_name == "Customer"
        assert customer.phone == "+380000000000"

    def test_rejects_existing_staff_without_disclosing_their_status(
        self, api_factory: Callable[[User, int], AuthContext]
    ) -> None:
        restaurant = Restaurant.objects.create(name="Test Restaurant")
        other_restaurant = Restaurant.objects.create(name="Other Restaurant")
        admin = UserFactory.create(role=RoleCode.ADMIN, restaurant=restaurant)
        employee = UserFactory.create(role=RoleCode.COOK, restaurant=other_restaurant)

        response = api_factory(admin, restaurant.id).client.post(
            self.url,
            {"email": employee.email, "role": RoleCode.WAITER},
            format="json",
        )

        assert response.status_code == 400
        assert response.data["email"] == [self.unavailable_user_message]
        employee.refresh_from_db()
        assert employee.restaurant_id == other_restaurant.id
        assert employee.role == RoleCode.COOK

    def test_rejects_unknown_email_without_disclosing_registration(
        self, api_factory: Callable[[User, int], AuthContext]
    ) -> None:
        restaurant = Restaurant.objects.create(name="Test Restaurant")
        admin = UserFactory.create(role=RoleCode.ADMIN, restaurant=restaurant)

        response = api_factory(admin, restaurant.id).client.post(
            self.url,
            {"email": "unknown@example.com", "role": RoleCode.WAITER},
            format="json",
        )

        assert response.status_code == 400
        assert response.data["email"] == [self.unavailable_user_message]
        assert User.objects.filter(email="unknown@example.com").exists() is False
