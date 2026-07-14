# mypy: disable-error-code="no-untyped-call"
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.authentication.models import RoleCode
from apps.orders.models import Session
from apps.reservations.models import ReservationType
from apps.restaurants.models import Restaurant, Table, Zone


@pytest.mark.django_db
def test_seed_orders_sets_ends_at_for_walk_in_sessions(
    restaurant: Restaurant,
    user_factory,
    item,
) -> None:
    zone, _ = Zone.objects.get_or_create(restaurant=restaurant, defaults={"name": "Main Hall"})
    table = Table.objects.create(restaurant=restaurant, public_number="T1", capacity=4, zone=zone, active=True)
    user = user_factory(role=RoleCode.WAITER, restaurant=restaurant)
    user.save()

    call_command("seed_orders", restaurant_id=restaurant.id)

    session = Session.objects.get(table=table, reservation__type=ReservationType.WALK_IN)
    assert session.ends_at is not None
    assert session.ends_at == session.reservation.end_at
    assert session.ends_at - timezone.now() <= timedelta(hours=2, minutes=5)
