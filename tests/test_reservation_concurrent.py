import concurrent.futures
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework import status

from apps.authentication.models import RoleCode
from apps.restaurants.models import Restaurant, Table

from .conftest import AuthContext


@pytest.mark.django_db(transaction=True)
def test_concurrent_reservation_slot_yields_exactly_one_success(
    restaurant: Restaurant,
    table: Table,
    user_factory: Callable[..., Any],
    api_factory: Callable[..., AuthContext],
) -> None:
    now = timezone.now()
    start_at = (now + timedelta(hours=1)).isoformat()
    end_at = (now + timedelta(hours=2)).isoformat()

    payload = {
        "table": str(table.public_id),
        "guest_count": 2,
        "start_at": start_at,
        "end_at": end_at,
    }
    url = "/api/reservations/reservations/"
    attempts = 100

    customer = user_factory(role=RoleCode.CUSTOMER)

    def _attempt() -> int:
        client, _ = api_factory(user=customer, restaurant_id=restaurant.id)
        return client.post(url, payload, format="json").status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(attempts, 50)) as pool:
        futures = [pool.submit(_attempt) for _ in range(attempts)]
        status_codes = [f.result() for f in concurrent.futures.as_completed(futures)]

    success_count = status_codes.count(status.HTTP_201_CREATED)
    conflict_count = status_codes.count(status.HTTP_409_CONFLICT)

    assert success_count == 1, f"Expected 1 success (201), got {success_count}"
    assert conflict_count == attempts - 1, f"Expected {attempts - 1} conflicts (409), got {conflict_count}"
    assert len(status_codes) == attempts
