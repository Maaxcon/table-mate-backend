from typing import Any

import pytest
from django.utils import timezone

from apps.authentication.models import RoleCode

pytestmark = [pytest.mark.django_db]


def _shift_data(employee_id: str, date: str | None = None) -> dict[str, Any]:
    return {
        "employee": employee_id,
        "date": date or timezone.now().date().isoformat(),
        "start_time": "09:00",
        "end_time": "17:00",
        "notes": "",
    }


class TestCreateShift:
    def test_admin_can_create_shift(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        employee = user_factory(role=RoleCode.WAITER)
        employee.save()
        employee.restaurant_id = restaurant.id
        employee.save(update_fields=["restaurant_id"])

        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        data = _shift_data(str(employee.public_id))
        resp = auth.client.post("/api/shifts/", data, format="json")

        assert resp.status_code == 201
        assert resp.data["employee"] == str(employee.public_id)
        assert resp.data["date"] == data["date"]
        assert resp.data["start_time"] == "09:00:00"
        assert resp.data["end_time"] == "17:00:00"
        assert resp.data["duration_hours"] == 8.0

    def test_create_shift_assigns_restaurant_from_auth(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        employee = user_factory(role=RoleCode.WAITER)
        employee.save()
        employee.restaurant_id = restaurant.id
        employee.save(update_fields=["restaurant_id"])

        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        data = _shift_data(str(employee.public_id))
        resp = auth.client.post("/api/shifts/", data, format="json")

        assert resp.status_code == 201
        shift_id = resp.data["public_id"]
        from apps.shifts.models import Shift
        shift = Shift.objects.get(public_id=shift_id)
        assert shift.restaurant_id == restaurant.id


class TestUpdateShift:
    def test_admin_can_update_shift_end_time(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        employee = user_factory(role=RoleCode.WAITER)
        employee.save()
        employee.restaurant_id = restaurant.id
        employee.save(update_fields=["restaurant_id"])

        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        data = _shift_data(str(employee.public_id))
        create_resp = auth.client.post("/api/shifts/", data, format="json")
        shift_id = create_resp.data["public_id"]

        patch_resp = auth.client.patch(
            f"/api/shifts/{shift_id}/",
            {"end_time": "18:00"},
            format="json",
        )

        assert patch_resp.status_code == 200
        assert patch_resp.data["end_time"] == "18:00:00"
        assert patch_resp.data["duration_hours"] == 9.0

    def test_update_invalid_end_time_before_start(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        employee = user_factory(role=RoleCode.WAITER)
        employee.save()
        employee.restaurant_id = restaurant.id
        employee.save(update_fields=["restaurant_id"])

        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        data = _shift_data(str(employee.public_id))
        create_resp = auth.client.post("/api/shifts/", data, format="json")
        shift_id = create_resp.data["public_id"]

        patch_resp = auth.client.patch(
            f"/api/shifts/{shift_id}/",
            {"end_time": "08:00"},
            format="json",
        )

        assert patch_resp.status_code == 400


class TestDeleteShift:
    def test_admin_can_delete_shift(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        employee = user_factory(role=RoleCode.WAITER)
        employee.save()
        employee.restaurant_id = restaurant.id
        employee.save(update_fields=["restaurant_id"])

        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        data = _shift_data(str(employee.public_id))
        create_resp = auth.client.post("/api/shifts/", data, format="json")
        shift_id = create_resp.data["public_id"]

        del_resp = auth.client.delete(f"/api/shifts/{shift_id}/")

        assert del_resp.status_code == 204

    def test_delete_nonexistent_shift_returns_404(self, api: Any, restaurant: Any) -> None:
        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        resp = auth.client.delete("/api/shifts/nonexistent-uuid/")
        assert resp.status_code == 404


class TestValidation:
    def test_end_time_before_start_time_returns_400(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        employee = user_factory(role=RoleCode.WAITER)
        employee.save()
        employee.restaurant_id = restaurant.id
        employee.save(update_fields=["restaurant_id"])

        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        data = {
            "employee": str(employee.public_id),
            "date": timezone.now().date().isoformat(),
            "start_time": "17:00",
            "end_time": "09:00",
        }
        resp = auth.client.post("/api/shifts/", data, format="json")

        assert resp.status_code == 400

    def test_shift_must_have_employee(self, api: Any, restaurant: Any) -> None:
        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        data = {
            "date": timezone.now().date().isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
        }
        resp = auth.client.post("/api/shifts/", data, format="json")

        assert resp.status_code == 400
