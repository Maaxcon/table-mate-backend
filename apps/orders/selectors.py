from __future__ import annotations

import uuid
from collections.abc import MutableMapping
from typing import cast

from django.db.models import Avg, CharField, Count, F, OuterRef, QuerySet, Subquery, Value
from django.db.models.functions import Coalesce, Concat, Extract, Trim

from apps.authentication.models import User
from apps.menu.models import MenuItem
from apps.reservations.models import Reservation
from apps.reservations.selectors import get_reservation_participant_ids

from .models import CartItem, CartSession, OrderItem, OrderItemStatus, Session, Ticket, TicketStatus


def get_session(session_id: uuid.UUID, restaurant_id: int) -> Session | None:
    """Return the restaurant's session by public id, or None if it doesn't exist."""
    return Session.objects.filter(public_id=session_id, restaurant_id=restaurant_id).first()


def get_kitchen_tickets(
    restaurant_id: int,
    *,
    status: str | None = None,
    session_public_id: str | None = None,
    order_public_id: str | None = None,
) -> QuerySet[Ticket]:
    """Return tickets annotated with table_number, server_name, guest_count, items_count.

    Results are ordered by injected_at (FIFO) per the constitution's injection-time
    ordering rule.
    """
    items_count_subq = (
        OrderItem.objects.filter(ticket=OuterRef("pk"))
        .exclude(status__in=[OrderItemStatus.VOIDED, OrderItemStatus.SERVED])
        .values("ticket")
        .annotate(count=Count("id"))
        .values("count")
    )

    qs = (
        Ticket.objects.select_related(
            "session__table",
            "order__created_by",
            "session",
            "restaurant",
        )
        .prefetch_related("items")
        .annotate(
            table_number=F("session__table__public_number"),
            server_name=Trim(
                Concat(
                    F("order__created_by__first_name"),
                    Value(" "),
                    F("order__created_by__last_name"),
                    output_field=CharField(),
                )
            ),
            guest_count=F("session__guest_count"),
            items_count=Coalesce(Subquery(items_count_subq), 0),
        )
        .filter(restaurant_id=restaurant_id, items_count__gt=0)
        .order_by("injected_at", "id")
    )

    if status is not None:
        qs = qs.filter(status=status)

    if session_public_id is not None:
        qs = qs.filter(session__public_id=session_public_id)

    if order_public_id is not None:
        qs = qs.filter(order__public_id=order_public_id)

    return qs


def get_kitchen_order_items(
    restaurant_id: int,
    *,
    ticket_id: str | None = None,
    status: str | None = None,
    session_public_id: str | None = None,
    order_public_id: str | None = None,
) -> QuerySet[OrderItem]:
    """Return order items for kitchen kanban view, filtered by ticket or status."""
    qs = (
        OrderItem.objects.select_related("menu_item__category", "ticket", "order__session", "restaurant")
        .filter(restaurant_id=restaurant_id)
        .order_by("created_at", "id")
    )

    if ticket_id is not None:
        qs = qs.filter(ticket__public_id=ticket_id)

    if status is not None:
        qs = qs.filter(status=status)

    if session_public_id is not None:
        qs = qs.filter(order__session__public_id=session_public_id)

    if order_public_id is not None:
        qs = qs.filter(order__public_id=order_public_id)

    return qs


def compute_avg_prep_time(restaurant_id: int) -> float | None:
    """Compute average cycle time (completed_at - injected_at) in seconds.

    Constitution Principle C9: cycle time must be derived from raw ticket records
    at query time, not stored as a precomputed column.
    """
    result = (
        Ticket.objects.filter(
            restaurant_id=restaurant_id,
            status=TicketStatus.COMPLETED,
            completed_at__isnull=False,
            injected_at__isnull=False,
        )
        .annotate(
            cycle_seconds=Extract(
                F("completed_at") - F("injected_at"),
                "epoch",
            ),
        )
        .aggregate(avg_cycle_seconds=Avg("cycle_seconds"))
    )

    return result.get("avg_cycle_seconds")


__all__ = [
    "compute_avg_prep_time",
    "get_cart_item",
    "get_cart_session",
    "get_kitchen_order_items",
    "get_kitchen_tickets",
    "get_menu_item",
    "get_reservation",
    "get_session",
    "is_cart_participant",
]


def _resolve_allowed_reservation_participant_ids(reservation: Reservation) -> set[int]:
    participant_ids = set(get_reservation_participant_ids(reservation))
    if reservation.customer_id:
        participant_ids.add(reservation.customer_id)
    return participant_ids


def is_cart_participant(user: User, session: CartSession) -> bool:
    cache = cast(MutableMapping[int, bool], session.__dict__.setdefault("_participant_cache", {}))

    user_id = user.id
    cached_value = cache.get(user_id)
    if cached_value is not None:
        return cached_value

    is_participant = session.participants.filter(id=user_id).exists()
    if not is_participant:
        reservation = session.reservation
        allowed_participants = _resolve_allowed_reservation_participant_ids(reservation)
        is_participant = user_id in allowed_participants

    cache[user_id] = is_participant
    return is_participant


def get_cart_session(restaurant_id: int, session_pk: str) -> CartSession | None:
    return (
        CartSession.objects.select_related("restaurant", "reservation")
        .filter(public_id=session_pk, restaurant_id=restaurant_id)
        .first()
    )


def get_cart_session_by_public_id(session_pk: str) -> CartSession | None:
    """Look up a cart session without a restaurant_id to scope by.

    A logged-in customer's JWT doesn't carry a restaurant_id claim (only staff
    tokens do — see CustomTokenObtainPairSerializer), so customer-facing
    lookups can't filter by it. public_id is globally unique, and the real
    authorization boundary is the participant check callers run afterward.
    """
    return CartSession.objects.select_related("restaurant", "reservation").filter(public_id=session_pk).first()


def get_cart_item(restaurant_id: int, item_id: str, session: CartSession) -> CartItem | None:
    return CartItem.objects.filter(public_id=item_id, cart_session=session, restaurant_id=restaurant_id).first()


def get_reservation(restaurant_id: int, reservation_id: str) -> Reservation | None:
    return Reservation.objects.filter(public_id=reservation_id, restaurant_id=restaurant_id).first()


def get_menu_item(restaurant_id: int, menu_item_id: str, *, for_update: bool = False) -> MenuItem | None:
    qs = MenuItem.objects.filter(public_id=menu_item_id, restaurant_id=restaurant_id)
    if for_update:
        qs = qs.select_for_update()
    return qs.first()
