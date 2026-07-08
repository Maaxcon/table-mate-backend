from collections.abc import Iterable
from datetime import datetime, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from apps.orders.models import Session, SessionStatus
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


# How long we assume a table with a currently open session will stay
# occupied, measured from "right now" — fixed, not derived from whatever the
# new booking being checked happens to request. Tying it to the requested
# duration would make the same start time read as free for a short booking
# but blocked for a long one, at the exact same instant: the table's actual
# occupancy doesn't depend on what a prospective new guest wants.
SESSION_GRACE_PERIOD = timedelta(minutes=30)


def get_session_grace_cutoffs(
    restaurant_id: int,
    table_ids: Iterable[int] | None,
    now: datetime,
    current_reservation_id: int | None = None,
) -> dict[int, datetime]:
    """For each table with a currently OPEN session, the instant it can be
    considered free again: whichever is later, its reservation's booked end,
    or `now + SESSION_GRACE_PERIOD` (they're seated right now and likely to
    stay at least that long). Batchable — call once and reuse across many
    slots instead of re-querying per slot.

    `current_reservation_id` excludes that reservation's own session — a
    guest prolonging their own active (seated) reservation must not have
    their own session block the extension.

    Also requires the linked reservation to still be ACTIVE — an OPEN session
    should always imply that, but if some path ever cancels/completes a
    reservation without also closing its session (a data-integrity bug, not a
    normal state), this recomputes "occupied until now + grace" on every
    single check, forever, since there's no reservation end to age it out.
    Guarding on reservation status here means a table can't get stuck looking
    permanently occupied just because a session was left dangling.
    """
    grace_until = now + SESSION_GRACE_PERIOD
    qs = Session.objects.filter(
        status=SessionStatus.OPEN,
        reservation__restaurant_id=restaurant_id,
        reservation__status=ReservationStatus.ACTIVE,
    )
    if table_ids is not None:
        qs = qs.filter(table_id__in=table_ids)
    if current_reservation_id is not None:
        qs = qs.exclude(reservation_id=current_reservation_id)

    cutoffs: dict[int, datetime] = {}
    for table_id, res_end in qs.values_list("table_id", "reservation__end_at"):
        until = max(res_end, grace_until) if res_end else grace_until
        if table_id not in cutoffs or until > cutoffs[table_id]:
            cutoffs[table_id] = until
    return cutoffs


def get_unavailable_table_ids(
    *,
    restaurant_id: int,
    start_at: datetime,
    end_at: datetime,
    table_ids: Iterable[int] | None = None,
    current_reservation_id: int | None = None,
    now: datetime | None = None,
) -> set[int]:
    """Ids of tables on this restaurant that are NOT bookable for
    [start_at, end_at).

    A table is unavailable when either an overlapping pending/active
    reservation already claims it, or it currently has an open session that
    may still occupy it once the window starts — a walk-in seated after its
    booked start, or guests overstaying past their booked end.

    This is the single source of truth for "is this table free": the floor
    editor's available-tables lookup, the reservation-conflict check on
    create/reschedule, and the customer-facing availability map all call it,
    so they can't disagree about the same table/slot.
    """
    reservations = Reservation.objects.filter(restaurant_id=restaurant_id, status__in=ACTIVE_STATUSES)
    if table_ids is not None:
        reservations = reservations.filter(table_id__in=table_ids)
    if current_reservation_id is not None:
        reservations = reservations.exclude(id=current_reservation_id)

    unavailable = set(
        reservations.filter(start_at__lt=end_at, end_at__gt=start_at).values_list("table_id", flat=True)
    )

    cutoffs = get_session_grace_cutoffs(
        restaurant_id,
        table_ids,
        now or timezone.now(),
        current_reservation_id,
    )
    unavailable.update(table_id for table_id, until in cutoffs.items() if start_at < until)

    return unavailable
