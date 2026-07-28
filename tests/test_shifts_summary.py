from typing import Any

import pytest

from apps.authentication.models import RoleCode

pytestmark = [pytest.mark.django_db]


class TestMonthSummary:
    def _create_shift(self, client: Any, employee_id: str, date: str, start: str = "09:00", end: str = "17:00") -> Any:
        return client.post("/api/shifts/", {
            "employee": employee_id,
            "date": date,
            "start_time": start,
            "end_time": end,
            "notes": "",
        }, format="json")

    def test_month_summary_returns_total_hours_and_shifts(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        emp = user_factory(role=RoleCode.WAITER)
        emp.save()
        emp.restaurant_id = restaurant.id
        emp.save(update_fields=["restaurant_id"])

        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        self._create_shift(auth.client, str(emp.public_id), "2026-07-01")
        self._create_shift(auth.client, str(emp.public_id), "2026-07-02", start="10:00", end="14:00")

        resp = auth.client.get("/api/shifts/month_summary/", {"year": 2026, "month": 7})

        assert resp.status_code == 200
        assert resp.data["total_hours"] == 12.0
        assert len(resp.data["shifts"]) == 2

    def test_month_summary_empty_month(self, api: Any, restaurant: Any) -> None:
        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        resp = auth.client.get("/api/shifts/month_summary/", {"year": 2025, "month": 1})

        assert resp.status_code == 200
        assert resp.data["total_hours"] == 0.0
        assert resp.data["shifts"] == []

    def test_month_summary_filters_by_employee(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        emp1 = user_factory(role=RoleCode.WAITER)
        emp1.save()
        emp1.restaurant_id = restaurant.id
        emp1.save(update_fields=["restaurant_id"])
        emp2 = user_factory(role=RoleCode.COOK)
        emp2.save()
        emp2.restaurant_id = restaurant.id
        emp2.save(update_fields=["restaurant_id"])

        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        self._create_shift(auth.client, str(emp1.public_id), "2026-07-01")
        self._create_shift(auth.client, str(emp2.public_id), "2026-07-01")

        resp = auth.client.get("/api/shifts/month_summary/", {
            "year": 2026,
            "month": 7,
            "employee_id": str(emp1.public_id),
        })

        assert resp.status_code == 200
        assert len(resp.data["shifts"]) == 1
        assert resp.data["shifts"][0]["employee_id"] == str(emp1.public_id)

    def test_month_summary_includes_duration_per_shift(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        emp = user_factory(role=RoleCode.WAITER)
        emp.save()
        emp.restaurant_id = restaurant.id
        emp.save(update_fields=["restaurant_id"])

        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        self._create_shift(auth.client, str(emp.public_id), "2026-07-01", start="09:00", end="17:00")

        resp = auth.client.get("/api/shifts/month_summary/", {"year": 2026, "month": 7})

        assert resp.status_code == 200
        shift = resp.data["shifts"][0]
        assert shift["duration_hours"] == 8.0
        assert "employee_name" in shift
        assert "employee_role" in shift

    def test_month_summary_requires_year_and_month(self, api: Any, restaurant: Any) -> None:
        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        resp = auth.client.get("/api/shifts/month_summary/")
        assert resp.status_code == 400

    def test_staff_can_access_month_summary(self, api: Any, restaurant: Any) -> None:
        auth = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
        resp = auth.client.get("/api/shifts/month_summary/", {"year": 2026, "month": 1})
        assert resp.status_code == 200
