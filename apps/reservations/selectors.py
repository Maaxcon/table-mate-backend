from datetime import datetime

from django.db.models import QuerySet

from apps.restaurants.models import Table

from .models import Reservation, ReservationStatus


def get_reservations_for_table(
    table: Table,
    start_at: datetime,
    end_at: datetime,
) -> QuerySet[Reservation]:
    return Reservation.objects.filter(
        table=table,
        status=ReservationStatus.CONFIRMED,
        start_at__lt=end_at,
        end_at__gt=start_at,
    )


def get_customer_reservations(customer_id: int, restaurant_id: int) -> QuerySet[Reservation]:
    return Reservation.objects.filter(
        customer_id=customer_id,
        restaurant_id=restaurant_id,
    ).select_related("table", "customer")


def get_reservation_by_id(reservation_id: str, restaurant_id: int) -> Reservation | None:
    return Reservation.objects.filter(public_id=reservation_id, restaurant_id=restaurant_id).first()
