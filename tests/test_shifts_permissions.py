from typing import Any

import pytest
from django.utils import timezone

from apps.authentication.models import RoleCode

pytestmark = [pytest.mark.django_db]


def _create_shift_via_api(client: Any, employee_id: str) -> Any:
    return client.post("/api/shifts/", {
        "employee": employee_id,
        "date": timezone.now().date().isoformat(),
        "start_time": "09:00",
        "end_time": "17:00",
        "notes": "",
    }, format="json")


class TestShiftPermissions:
    def test_admin_can_create_shift(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        emp = user_factory(role=RoleCode.WAITER)
        emp.save()
        emp.restaurant_id = restaurant.id
        emp.save(update_fields=["restaurant_id"])
        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        resp = _create_shift_via_api(auth.client, str(emp.public_id))
        assert resp.status_code == 201

    def test_admin_can_update_shift(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        emp = user_factory(role=RoleCode.WAITER)
        emp.save()
        emp.restaurant_id = restaurant.id
        emp.save(update_fields=["restaurant_id"])
        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        create_resp = _create_shift_via_api(auth.client, str(emp.public_id))
        shift_id = create_resp.data["public_id"]
        resp = auth.client.patch(f"/api/shifts/{shift_id}/", {"end_time": "18:00"}, format="json")
        assert resp.status_code == 200

    def test_admin_can_delete_shift(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        emp = user_factory(role=RoleCode.WAITER)
        emp.save()
        emp.restaurant_id = restaurant.id
        emp.save(update_fields=["restaurant_id"])
        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        create_resp = _create_shift_via_api(auth.client, str(emp.public_id))
        shift_id = create_resp.data["public_id"]
        resp = auth.client.delete(f"/api/shifts/{shift_id}/")
        assert resp.status_code == 204

    def test_waiter_cannot_create_shift(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        emp = user_factory(role=RoleCode.WAITER)
        emp.save()
        emp.restaurant_id = restaurant.id
        emp.save(update_fields=["restaurant_id"])
        auth = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
        resp = _create_shift_via_api(auth.client, str(emp.public_id))
        assert resp.status_code == 403

    def test_cook_cannot_create_shift(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        emp = user_factory(role=RoleCode.COOK)
        emp.save()
        emp.restaurant_id = restaurant.id
        emp.save(update_fields=["restaurant_id"])
        auth = api(role=RoleCode.COOK, restaurant_id=restaurant.id)
        resp = _create_shift_via_api(auth.client, str(emp.public_id))
        assert resp.status_code == 403

    def test_waiter_cannot_update_shift(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        emp = user_factory(role=RoleCode.WAITER)
        emp.save()
        emp.restaurant_id = restaurant.id
        emp.save(update_fields=["restaurant_id"])
        admin_auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        create_resp = _create_shift_via_api(admin_auth.client, str(emp.public_id))
        shift_id = create_resp.data["public_id"]

        staff_auth = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
        resp = staff_auth.client.patch(f"/api/shifts/{shift_id}/", {"end_time": "18:00"}, format="json")
        assert resp.status_code == 403

    def test_waiter_cannot_delete_shift(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        emp = user_factory(role=RoleCode.WAITER)
        emp.save()
        emp.restaurant_id = restaurant.id
        emp.save(update_fields=["restaurant_id"])
        admin_auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        create_resp = _create_shift_via_api(admin_auth.client, str(emp.public_id))
        shift_id = create_resp.data["public_id"]

        staff_auth = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
        resp = staff_auth.client.delete(f"/api/shifts/{shift_id}/")
        assert resp.status_code == 403

    def test_staff_can_list_shifts(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        emp = user_factory(role=RoleCode.WAITER)
        emp.save()
        emp.restaurant_id = restaurant.id
        emp.save(update_fields=["restaurant_id"])
        auth = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
        resp = auth.client.get("/api/shifts/", {"date": timezone.now().date().isoformat()})
        assert resp.status_code == 200

    def test_customer_cannot_access_shifts(self, api: Any, restaurant: Any) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        resp = auth.client.get("/api/shifts/")
        assert resp.status_code == 403

    def test_customer_cannot_access_month_summary(self, api: Any, restaurant: Any) -> None:
        auth = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        resp = auth.client.get("/api/shifts/month_summary/", {"year": 2026, "month": 7})
        assert resp.status_code == 403
