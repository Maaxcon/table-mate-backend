from typing import Any

import pytest
from django.utils import timezone

from apps.authentication.models import RoleCode

pytestmark = [pytest.mark.django_db]


class TestListShifts:
    def _create_shift(self, client: Any, employee_id: str, date: str, start: str = "09:00", end: str = "17:00") -> Any:
        return client.post("/api/shifts/", {
            "employee": employee_id,
            "date": date,
            "start_time": start,
            "end_time": end,
            "notes": "",
        }, format="json")

    def test_list_returns_all_shifts_for_date(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        emp1 = user_factory(role=RoleCode.WAITER)
        emp1.save()
        emp1.restaurant_id = restaurant.id
        emp1.save(update_fields=["restaurant_id"])
        emp2 = user_factory(role=RoleCode.COOK)
        emp2.save()
        emp2.restaurant_id = restaurant.id
        emp2.save(update_fields=["restaurant_id"])

        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        today = timezone.now().date().isoformat()
        self._create_shift(auth.client, str(emp1.public_id), today)
        self._create_shift(auth.client, str(emp2.public_id), today)

        resp = auth.client.get("/api/shifts/", {"date": today})

        assert resp.status_code == 200
        assert len(resp.data["results"]) == 2

    def test_list_filters_by_employee(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        emp1 = user_factory(role=RoleCode.WAITER)
        emp1.save()
        emp1.restaurant_id = restaurant.id
        emp1.save(update_fields=["restaurant_id"])
        emp2 = user_factory(role=RoleCode.COOK)
        emp2.save()
        emp2.restaurant_id = restaurant.id
        emp2.save(update_fields=["restaurant_id"])

        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        today = timezone.now().date().isoformat()
        self._create_shift(auth.client, str(emp1.public_id), today)
        self._create_shift(auth.client, str(emp2.public_id), today)

        resp = auth.client.get("/api/shifts/", {"date": today, "employee_id": str(emp1.public_id)})

        assert resp.status_code == 200
        assert len(resp.data["results"]) == 1
        assert resp.data["results"][0]["employee"] == emp1.public_id

    def test_list_filters_by_date_range(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        emp = user_factory(role=RoleCode.WAITER)
        emp.save()
        emp.restaurant_id = restaurant.id
        emp.save(update_fields=["restaurant_id"])

        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        self._create_shift(auth.client, str(emp.public_id), "2026-07-01")
        self._create_shift(auth.client, str(emp.public_id), "2026-07-15")
        self._create_shift(auth.client, str(emp.public_id), "2026-08-01")

        resp = auth.client.get("/api/shifts/", {
            "date_from": "2026-07-01",
            "date_to": "2026-07-31",
        })

        assert resp.status_code == 200
        assert len(resp.data["results"]) == 2

    def test_list_returns_empty_when_no_shifts(self, api: Any, restaurant: Any) -> None:
        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        resp = auth.client.get("/api/shifts/", {"date": "2026-01-01"})
        assert resp.status_code == 200
        assert len(resp.data["results"]) == 0

    def test_list_rejects_invalid_employee_id(self, api: Any, restaurant: Any) -> None:
        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        resp = auth.client.get("/api/shifts/", {"employee_id": "me"})
        assert resp.status_code == 400

    @pytest.mark.parametrize("param", ["date", "date_from", "date_to"])
    def test_list_rejects_invalid_date_params(self, api: Any, restaurant: Any, param: str) -> None:
        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        resp = auth.client.get("/api/shifts/", {param: "13-45-2026"})
        assert resp.status_code == 400

    def test_list_returns_employee_details(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        emp = user_factory(role=RoleCode.WAITER)
        emp.save()
        emp.restaurant_id = restaurant.id
        emp.save(update_fields=["restaurant_id"])

        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        today = timezone.now().date().isoformat()
        self._create_shift(auth.client, str(emp.public_id), today)

        resp = auth.client.get("/api/shifts/", {"date": today})

        assert resp.status_code == 200
        result = resp.data["results"][0]
        assert "employee_name" in result
        assert "employee_role" in result
        assert result["employee_role"] == RoleCode.WAITER
