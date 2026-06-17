from datetime import datetime

from django.db.models import QuerySet
from django.utils import timezone

from apps.restaurants.models import Table

from .models import Reservation, ReservationParticipant, ReservationStatus


def get_active_reservation_for_table(table: Table) -> Reservation | None:
    """Return the reservation currently in progress on the table, or None.

    Active means status ACTIVE and now inside the [start_at, end_at) window.
    Walk-in and pre-booked are treated the same.
    """
    now = timezone.now()
    return (
        Reservation.objects.filter(
            table=table,
            status=ReservationStatus.ACTIVE,
            start_at__lte=now,
            end_at__gt=now,
        )
        .order_by("-created_at")
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


def get_customer_reservations(customer_id: int, restaurant_id: int) -> QuerySet[Reservation]:
    return Reservation.objects.filter(
        customer_id=customer_id,
        restaurant_id=restaurant_id,
        status__in=[ReservationStatus.PENDING, ReservationStatus.ACTIVE],
    ).select_related("table", "restaurant", "customer")


def get_customer_global_reservations(customer_id: int) -> QuerySet[Reservation]:
    return Reservation.objects.filter(
        customer_id=customer_id,
        status__in=[ReservationStatus.PENDING, ReservationStatus.ACTIVE],
    ).select_related("table", "restaurant", "customer")


def get_reservation_by_id(reservation_id: str, restaurant_id: int) -> Reservation | None:
    return Reservation.objects.filter(public_id=reservation_id, restaurant_id=restaurant_id).first()


def get_reservation_participant_ids(reservation: Reservation) -> list[int]:
    return list(ReservationParticipant.objects.filter(reservation=reservation).values_list("user_id", flat=True))
