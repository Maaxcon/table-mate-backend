from collections.abc import Callable

import pytest

from apps.authentication.models import RoleCode, User
from apps.restaurants.models import Restaurant
from tests.conftest import AuthContext, UserFactory


@pytest.mark.django_db
class TestEmployeeAssign:
    url = "/api/restaurants/employees/assign/"
    create_url = "/api/restaurants/employees/"
    unavailable_user_message = "This user cannot be assigned as staff."

    def test_create_endpoint_assigns_existing_customer(self, api_factory: Callable[[User, int], AuthContext]) -> None:
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
            self.create_url,
            {
                "email": customer.email,
                "staff_display_name": "Service team",
                "phone": "+380111111111",
                "role": RoleCode.WAITER,
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["role"] == RoleCode.WAITER
        customer.refresh_from_db()
        assert customer.restaurant_id == restaurant.id
        assert customer.is_active is False
        assert customer.first_name == "Existing"
        assert customer.last_name == "Customer"
        assert customer.phone == "+380000000000"
        assert customer.staff_display_name == "Service team"

    def test_create_endpoint_requires_staff_display_name_for_new_employee(
        self, api_factory: Callable[[User, int], AuthContext]
    ) -> None:
        restaurant = Restaurant.objects.create(name="Test Restaurant")
        admin = UserFactory.create(role=RoleCode.ADMIN, restaurant=restaurant)

        response = api_factory(admin, restaurant.id).client.post(
            self.create_url,
            {"email": "new@example.com", "role": RoleCode.WAITER},
            format="json",
        )

        assert response.status_code == 400
        assert response.data == {"staff_display_name": ["This field is required."]}
        assert User.objects.filter(email="new@example.com").exists() is False

    def test_create_endpoint_stores_staff_display_name_separately(
        self, api_factory: Callable[[User, int], AuthContext]
    ) -> None:
        restaurant = Restaurant.objects.create(name="Test Restaurant")
        admin = UserFactory.create(role=RoleCode.ADMIN, restaurant=restaurant)

        response = api_factory(admin, restaurant.id).client.post(
            self.create_url,
            {
                "email": "new@example.com",
                "staff_display_name": "Floor team",
                "role": RoleCode.WAITER,
            },
            format="json",
        )

        assert response.status_code == 201
        employee = User.objects.get(email="new@example.com")
        assert employee.staff_display_name == "Floor team"
        assert employee.first_name == ""
        assert employee.last_name == ""

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
