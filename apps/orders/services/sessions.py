"""Cart-session lifecycle: open, ensure-for-table, and stale cleanup."""

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.authentication.models import User
from apps.reservations.models import ReservationStatus
from apps.reservations.selectors import get_active_reservation_for_table
from apps.restaurants.models import Table
from common.exceptions import NoActiveReservationError, ReservationNotFoundError

from ..models import CartSession, CartSessionStatus
from ..selectors import _resolve_allowed_reservation_participant_ids, get_reservation


def create_cart_session(
    *,
    restaurant_id: int,
    reservation_id: str,
    user: User,
) -> CartSession:
    reservation = get_reservation(restaurant_id, reservation_id)
    if reservation is None:
        raise ReservationNotFoundError(f"Reservation {reservation_id} not found.")

    allowed_participants = _resolve_allowed_reservation_participant_ids(reservation)
    if not allowed_participants or user.id not in allowed_participants:
        raise PermissionDenied("Only reservation participants may open a cart session.")

    with transaction.atomic():
        existing = (
            CartSession.objects.select_for_update()
            .filter(reservation=reservation, status=CartSessionStatus.ACTIVE)
            .first()
        )
        if existing is not None:
            existing.participants.add(*allowed_participants)
            return existing
        try:
            with transaction.atomic():
                session = CartSession.objects.create(
                    restaurant_id=restaurant_id,
                    reservation=reservation,
                    created_by=user,
                )
        except IntegrityError:
            session = CartSession.objects.get(reservation=reservation, status=CartSessionStatus.ACTIVE)
        session.participants.add(*allowed_participants)
    return session


def ensure_active_cart_for_table(
    *,
    table: Table,
    user: User | None = None,
) -> CartSession:
    """Return (or create) the active cart session for the table's active reservation.

    Finds the reservation in progress on the table. Raises NoActiveReservationError
    if there is none. Safe under concurrent scans: relies on the
    one_active_per_reservation unique constraint so two callers can never create
    two active sessions for the same reservation.
    """
    reservation = get_active_reservation_for_table(table)
    if reservation is None:
        raise NoActiveReservationError(f"Table {table.public_id} has no active reservation.")

    with transaction.atomic():
        existing = (
            CartSession.objects.select_for_update()
            .filter(reservation=reservation, status=CartSessionStatus.ACTIVE)
            .first()
        )
        if existing is not None:
            if user is not None:
                existing.participants.add(user)
            return existing
        try:
            with transaction.atomic():
                session = CartSession.objects.create(
                    restaurant_id=reservation.restaurant_id,
                    reservation=reservation,
                    created_by=user,
                )
        except IntegrityError:
            session = CartSession.objects.get(reservation=reservation, status=CartSessionStatus.ACTIVE)
        if user is not None:
            session.participants.add(user)
    return session


def close_stale_cart_sessions() -> int:
    """Close active carts whose reservation is finished or past its end time.

    Keeps dead active CartSessions from piling up after a visit ends. Returns
    the number of carts closed. Time-valid active reservations are left alone.
    """
    now = timezone.now()
    stale = CartSession.objects.filter(status=CartSessionStatus.ACTIVE).filter(
        Q(reservation__status__in=[ReservationStatus.COMPLETED, ReservationStatus.CANCELLED])
        | Q(reservation__end_at__lt=now)
    )
    return stale.update(status=CartSessionStatus.CLOSED)
