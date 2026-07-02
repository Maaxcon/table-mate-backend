import concurrent.futures
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from django.db import IntegrityError, connection

from apps.authentication.models import RoleCode
from apps.menu.models import MenuItem
from apps.orders.models import Session, Ticket
from apps.orders.services import create_order_with_items, open_session
from apps.restaurants.models import Restaurant, Table


@pytest.mark.django_db(transaction=True)
def test_concurrent_order_submissions_yield_contiguous_daily_numbers(
    restaurant: Restaurant,
    table: Table,
    item: MenuItem,
    user_factory: Callable[..., Any],
) -> None:
    """N concurrent submissions must each get a distinct, contiguous T-number.

    Regression guard for the daily-number allocator: ``select_for_update()`` is a
    no-op on an aggregate query, so without a real lock concurrent
    ``create_order_with_items`` calls collided on the
    (restaurant, daily_seq_date, daily_number) unique constraint — one winner and
    N-1 ``IntegrityError`` rollbacks (each a lost order / 409 at rush).
    """
    actor = user_factory(role=RoleCode.WAITER)
    actor.save()
    session = open_session(
        restaurant_id=restaurant.id,
        table=table,
        guest_count=4,
        opened_by=actor,
        currency="UAH",
        opened_at=datetime.now(UTC).isoformat(),
        actor=actor,
    )

    workers = 8

    def _attempt() -> int | None:
        try:
            local_session = Session.objects.get(pk=session.pk)
            order = create_order_with_items(
                session=local_session,
                items=[{"menu_item": item, "guest_slot": 1, "quantity": 1, "comment": None}],
                actor=actor,
            )
            ticket = order.tickets.get()
            return ticket.daily_number
        except IntegrityError:
            return None
        finally:
            # Each worker uses its own connection; close it so the pool doesn't leak.
            connection.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_attempt) for _ in range(workers)]
        numbers = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert None not in numbers, f"Some submissions failed with IntegrityError: {numbers}"
    assert sorted(n for n in numbers if n is not None) == list(range(1, workers + 1))
    assert Ticket.objects.filter(session=session).count() == workers
