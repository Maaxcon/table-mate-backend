from typing import Any

import pytest

from apps.authentication.models import RoleCode
from apps.shifts.models import Shift

pytestmark = [pytest.mark.django_db]


class TestCopyShifts:
    def _create_shift(self, client: Any, employee_id: str, date: str, start: str = "09:00", end: str = "17:00") -> Any:
        return client.post("/api/shifts/", {
            "employee": employee_id,
            "date": date,
            "start_time": start,
            "end_time": end,
            "notes": "",
        }, format="json")

    def test_copy_shifts_to_target_dates(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        emp = user_factory(role=RoleCode.WAITER)
        emp.save()
        emp.restaurant_id = restaurant.id
        emp.save(update_fields=["restaurant_id"])

        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        self._create_shift(auth.client, str(emp.public_id), "2026-07-01")

        resp = auth.client.post("/api/shifts/copy/", {
            "source_date": "2026-07-01",
            "target_dates": ["2026-07-08", "2026-07-15"],
        }, format="json")

        assert resp.status_code == 201
        assert resp.data["copied"] == 2

    def test_copy_with_employee_filter(self, api: Any, restaurant: Any, user_factory: Any) -> None:
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

        resp = auth.client.post("/api/shifts/copy/", {
            "source_date": "2026-07-01",
            "target_dates": ["2026-07-08"],
            "employee_ids": [str(emp1.public_id)],
        }, format="json")

        assert resp.status_code == 201
        assert resp.data["copied"] == 1

    def test_copy_rejects_invalid_employee_ids(self, api: Any, restaurant: Any) -> None:
        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        resp = auth.client.post("/api/shifts/copy/", {
            "source_date": "2026-07-01",
            "target_dates": ["2026-07-08"],
            "employee_ids": ["me"],
        }, format="json")

        assert resp.status_code == 400

    def test_copy_rejects_outside_working_hours(
        self, api: Any, restaurant: Any, restaurant_settings: Any, user_factory: Any
    ) -> None:
        hours = dict(restaurant_settings.working_hours)
        hours["tue"] = {"open": "18:00", "close": "20:00"}
        restaurant_settings.working_hours = hours
        restaurant_settings.save(update_fields=["working_hours"])

        emp = user_factory(role=RoleCode.WAITER)
        emp.save()
        emp.restaurant_id = restaurant.id
        emp.save(update_fields=["restaurant_id"])

        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        self._create_shift(auth.client, str(emp.public_id), "2026-07-06", start="10:00", end="22:00")

        resp = auth.client.post("/api/shifts/copy/", {
            "source_date": "2026-07-06",
            "target_dates": ["2026-07-07"],
        }, format="json")

        assert resp.status_code == 400
        assert Shift.objects.filter(date="2026-07-07").count() == 0

    def test_copy_rejects_when_target_date_already_has_shift(
        self, api: Any, restaurant: Any, user_factory: Any
    ) -> None:
        emp = user_factory(role=RoleCode.WAITER)
        emp.save()
        emp.restaurant_id = restaurant.id
        emp.save(update_fields=["restaurant_id"])

        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        self._create_shift(auth.client, str(emp.public_id), "2026-07-01")
        self._create_shift(auth.client, str(emp.public_id), "2026-07-08")

        resp = auth.client.post("/api/shifts/copy/", {
            "source_date": "2026-07-01",
            "target_dates": ["2026-07-08"],
        }, format="json")

        assert resp.status_code == 409
        assert Shift.objects.filter(date="2026-07-08").count() == 1

    def test_copy_rejects_on_partial_overlap(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        emp = user_factory(role=RoleCode.WAITER)
        emp.save()
        emp.restaurant_id = restaurant.id
        emp.save(update_fields=["restaurant_id"])

        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        self._create_shift(auth.client, str(emp.public_id), "2026-07-01", start="09:00", end="12:00")
        self._create_shift(auth.client, str(emp.public_id), "2026-07-08", start="11:00", end="13:00")

        resp = auth.client.post("/api/shifts/copy/", {
            "source_date": "2026-07-01",
            "target_dates": ["2026-07-08"],
        }, format="json")

        assert resp.status_code == 409

    def test_copy_rejects_whole_copy_when_one_employee_overlaps(
        self, api: Any, restaurant: Any, user_factory: Any
    ) -> None:
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
        self._create_shift(auth.client, str(emp1.public_id), "2026-07-08")

        resp = auth.client.post("/api/shifts/copy/", {
            "source_date": "2026-07-01",
            "target_dates": ["2026-07-08"],
        }, format="json")

        assert resp.status_code == 409
        assert Shift.objects.filter(employee=emp2, date="2026-07-08").count() == 0

    def test_copy_empty_source_returns_0_copied(self, api: Any, restaurant: Any) -> None:
        auth = api(role=RoleCode.ADMIN, restaurant_id=restaurant.id)
        resp = auth.client.post("/api/shifts/copy/", {
            "source_date": "2026-07-01",
            "target_dates": ["2026-07-08"],
        }, format="json")

        assert resp.status_code == 201
        assert resp.data["copied"] == 0

    def test_copy_requires_admin(self, api: Any, restaurant: Any, user_factory: Any) -> None:
        emp = user_factory(role=RoleCode.WAITER)
        emp.save()
        emp.restaurant_id = restaurant.id
        emp.save(update_fields=["restaurant_id"])

        auth = api(role=RoleCode.WAITER, restaurant_id=restaurant.id)
        resp = auth.client.post("/api/shifts/copy/", {
            "source_date": "2026-07-01",
            "target_dates": ["2026-07-08"],
        }, format="json")

        assert resp.status_code == 403
