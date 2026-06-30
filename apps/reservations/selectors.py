from datetime import datetime

from django.db.models import QuerySet
from django.utils import timezone

from apps.restaurants.models import Table

from .models import Reservation, ReservationParticipant, ReservationStatus


def get_active_reservation_for_table(table: Table) -> Reservation | None:
    """Return the reservation currently in progress on the table, or None.

    Once a reservation is ACTIVE the table is open, so the cart stays available
    for the whole visit until end_at — no lower bound on start_at (a guest may
    scan/seat a few minutes early). Expired reservations (end_at passed) yield
    nothing. Walk-in and pre-booked are treated the same.
    """
    now = timezone.now()
    return (
        Reservation.objects.filter(
            table=table,
            status=ReservationStatus.ACTIVE,
            end_at__gt=now,
        )
        .order_by("-created_at")
        .first()
    )


def get_upcoming_pending_reservation_for_table(table: Table) -> Reservation | None:
    """Return the soonest pending (not yet activated) booking on the table, or None.

    Used when a guest opens the table link before the table is active: tells them
    a booking exists and when it starts, instead of a blunt "no booking" message.
    Only bookings whose window has not already passed are considered.
    """
    now = timezone.now()
    return (
        Reservation.objects.filter(
            table=table,
            status=ReservationStatus.PENDING,
            end_at__gt=now,
        )
        .order_by("start_at")
        .first()
    )


def get_reservations_for_table(
    table: Table,
    start_at: datetime,
    end_at: datetime,
) -> QuerySet[Reservation]:
    return Reservation.objects.filter(
        table=table,
        status=ReservationStatus.ACTIVE,
        start_at__lt=end_at,
        end_at__gt=start_at,
    )


ACTIVE_STATUSES: list[str] = [ReservationStatus.PENDING, ReservationStatus.ACTIVE]
PAST_STATUSES: list[str] = [ReservationStatus.COMPLETED, ReservationStatus.CANCELLED]


def get_customer_reservations(
    customer_id: int,
    restaurant_id: int,
    statuses: list[str] | None = None,
) -> QuerySet[Reservation]:
    return Reservation.objects.filter(
        customer_id=customer_id,
        restaurant_id=restaurant_id,
        status__in=statuses or ACTIVE_STATUSES,
    ).select_related("table", "restaurant", "customer")


def get_customer_global_reservations(
    customer_id: int,
    statuses: list[str] | None = None,
) -> QuerySet[Reservation]:
    return Reservation.objects.filter(
        customer_id=customer_id,
        status__in=statuses or ACTIVE_STATUSES,
    ).select_related("table", "restaurant", "customer")


def get_reservation_by_id(reservation_id: str, restaurant_id: int) -> Reservation | None:
    return Reservation.objects.filter(public_id=reservation_id, restaurant_id=restaurant_id).first()


def get_reservation_participant_ids(reservation: Reservation) -> list[int]:
    return list(ReservationParticipant.objects.filter(reservation=reservation).values_list("user_id", flat=True))
