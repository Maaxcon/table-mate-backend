from datetime import datetime, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.authentication.models import RoleCode, User
from apps.restaurants.models import Table
from common.exceptions import ReservationConflictError
from common.hall_events import emit_hall_new_reservation

from ..editor.selectors import get_available_tables
from .models import Reservation, ReservationStatus, ReservationType


def check_availability(
    restaurant_id: int,
    table_id: str,
    start_at: datetime,
    end_at: datetime,
    current_reservation_id: int | None = None,
) -> bool:
    available = get_available_tables(
        restaurant_id=restaurant_id,
        start_at=start_at,
        end_at=end_at,
        current_reservation_id=current_reservation_id,
    )
    return available.filter(public_id=table_id).exists()


def _check_reservation_conflict(
    *,
    restaurant_id: int,
    table: Table,
    start_at: datetime,
    end_at: datetime,
    current_reservation_id: int | None = None,
) -> None:
    qs = Reservation.objects.filter(
        restaurant_id=restaurant_id,
        table=table,
        status__in=[ReservationStatus.PENDING, ReservationStatus.ACTIVE],
        start_at__lt=end_at,
        end_at__gt=start_at,
    )
    if current_reservation_id is not None:
        qs = qs.exclude(id=current_reservation_id)
    if qs.exists():
        raise ReservationConflictError("Table is not available during the requested time.")


@transaction.atomic
def create_reservation(
    *,
    restaurant_id: int,
    customer_id: int,
    table_id: str,
    guest_count: int,
    start_at: datetime,
    end_at: datetime,
    notes: str | None = None,
    actor: User | None = None,
) -> Reservation:
    table = (
        Table.objects.filter(restaurant_id=restaurant_id, public_id=table_id, active=True).select_for_update().first()
    )

    if not table:
        raise NotFound("Table not found or inactive.")

    _check_reservation_conflict(
        restaurant_id=restaurant_id,
        table=table,
        start_at=start_at,
        end_at=end_at,
    )

    reservation = Reservation.objects.create(
        restaurant_id=restaurant_id,
        customer_id=customer_id,
        table=table,
        guest_count=guest_count,
        start_at=start_at,
        end_at=end_at,
        status=ReservationStatus.PENDING,
        notes=notes or "",
    )

    if actor is not None:
        emit_hall_new_reservation(
            restaurant_id,
            reservation_id=str(reservation.public_id),
            table_id=str(table.public_id),
            start_at=start_at.isoformat(),
            end_at=end_at.isoformat(),
            actor=actor,
        )

    return reservation


@transaction.atomic
def seat_walk_in_customer(table: Table, guest_count: int) -> Reservation:
    end_at = timezone.now() + timedelta(hours=2)

    reservation = Reservation.objects.create(
        table=table,
        restaurant_id=table.restaurant_id,
        guest_count=guest_count,
        start_at=timezone.now(),
        end_at=end_at,
        type=ReservationType.WALK_IN,
        status=ReservationStatus.ACTIVE,
        customer=None,
    )

    return reservation


@transaction.atomic
def reschedule_reservation(
    reservation: Reservation,
    validated_data: dict[str, Any],
) -> Reservation:
    table = validated_data.get("table", reservation.table)
    if table is None:
        raise ReservationConflictError("Table not found or inactive.")
    table = Table.objects.select_for_update().get(id=table.id)

    start_at = validated_data.get("start_at", reservation.start_at)
    end_at = validated_data.get("end_at", reservation.end_at)

    _check_reservation_conflict(
        restaurant_id=reservation.restaurant_id,
        table=table,
        start_at=start_at,
        end_at=end_at,
        current_reservation_id=reservation.id,
    )

    fields_to_update = ["table", "guest_count", "start_at", "end_at", "notes"]
    for field in fields_to_update:
        if field in validated_data:
            setattr(reservation, field, validated_data[field])

    reservation.save()
    return reservation


_STATUS_TRANSITIONS: dict[str, set[str]] = {
    ReservationStatus.PENDING: {ReservationStatus.ACTIVE, ReservationStatus.CANCELLED},
    ReservationStatus.ACTIVE: {ReservationStatus.COMPLETED, ReservationStatus.CANCELLED},
}

_ALLOWED_ROLES: frozenset[str] = frozenset({RoleCode.ADMIN, RoleCode.WAITER})


@transaction.atomic
def update_reservation_status(
    reservation: Reservation,
    *,
    new_status: str,
    actor: User,
) -> Reservation:
    if actor.role not in _ALLOWED_ROLES:
        raise PermissionDenied("Only admin and waiter roles may update reservation status.")

    allowed = _STATUS_TRANSITIONS.get(reservation.status, set())
    if new_status not in allowed:
        raise ReservationConflictError(f"Cannot transition reservation from '{reservation.status}' to '{new_status}'.")

    reservation.status = new_status
    reservation.save(update_fields=["status", "updated_at"])
    return reservation
