from datetime import datetime, timedelta
from itertools import cycle
from typing import Any

from django.core.management.base import BaseCommand
from django.db import models, transaction
from django.utils import timezone

from apps.authentication.models import RoleCode, User
from apps.menu.models import MenuItem
from apps.orders.models import (
    CreatedBySource,
    Order,
    OrderItem,
    OrderItemStatus,
    OrderSource,
    OrderStatus,
    Session,
    SessionStatus,
    Ticket,
    TicketStatus,
)
from apps.reservations.models import Reservation, ReservationStatus, ReservationType
from apps.restaurants.models import Restaurant, Table

WALKIN_SESSION_COUNT = 3

# Demo ticket profiles, cycled per session so the kitchen kanban is populated
# across every column and urgency band (≥7m amber, ≥12m red on the frontend).
# minutes_ago values are offsets from "now"; prep_min only applies to completed.
TICKET_PROFILES: list[dict[str, Any]] = [
    {"status": TicketStatus.ACTIVE, "injected_min": 4, "started_min": 4, "items": "mixed"},
    {"status": TicketStatus.INCOMING, "injected_min": 2, "items": "all_pending"},
    {"status": TicketStatus.ACTIVE, "injected_min": 6, "started_min": 6, "items": "all_ready"},
    {"status": TicketStatus.INCOMING, "injected_min": 9, "items": "all_pending"},  # amber
    {"status": TicketStatus.ACTIVE, "injected_min": 11, "started_min": 11, "items": "mixed"},  # amber
    {"status": TicketStatus.COMPLETED, "injected_min": 25, "started_min": 20, "prep_min": 9, "items": "all_ready"},
    {"status": TicketStatus.INCOMING, "injected_min": 15, "items": "all_pending"},  # red
    {"status": TicketStatus.ACTIVE, "injected_min": 14, "started_min": 14, "items": "mixed"},  # red
    {"status": TicketStatus.COMPLETED, "injected_min": 33, "started_min": 27, "prep_min": 12, "items": "all_ready"},
]


class Command(BaseCommand):
    help = "Seed sessions, orders, tickets, and order items for demo purposes."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--restaurant-id",
            type=int,
            help="Restaurant ID to seed (seeds all if omitted)",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        restaurants = Restaurant.objects.all()
        if options["restaurant_id"]:
            restaurants = restaurants.filter(pk=options["restaurant_id"])

        now = timezone.now()

        for restaurant in restaurants:
            self.stdout.write(f"Seeding orders for: {restaurant.name}")

            staff = list(
                User.objects.filter(
                    restaurant=restaurant,
                    role__in=[RoleCode.ADMIN, RoleCode.WAITER],
                )
            )
            if not staff:
                self.stdout.write(self.style.WARNING(f"No staff for {restaurant.name}. Skipping."))
                continue

            waiter = staff[0]
            profiles = cycle(TICKET_PROFILES)

            menu_items = list(MenuItem.objects.filter(restaurant=restaurant).order_by("id"))
            if not menu_items:
                self.stdout.write(self.style.WARNING(f"No menu items for {restaurant.name}. Skipping."))

            # Build a category-diverse pool (one dish per distinct category) so the
            # kanban shows dishes spanning multiple categories — the kitchen board
            # colour-codes tickets by MenuItem.category. Fall back to all items when
            # there aren't enough categories to fill a ticket.
            items_pool: list[MenuItem] = []
            seen_categories: set[int | None] = set()
            for mi in menu_items:
                if mi.category_id not in seen_categories:
                    seen_categories.add(mi.category_id)
                    items_pool.append(mi)
            if len(items_pool) < 3:
                items_pool = menu_items

            # Rotates the starting category per session so adjacent tickets differ.
            session_seq = 0

            active_reservations = list(
                Reservation.objects.filter(
                    restaurant=restaurant,
                    table__isnull=False,
                    status=ReservationStatus.ACTIVE,
                ).select_related("table")
            )

            sessions_from_res = 0
            for res in active_reservations:
                if not res.table:
                    continue

                session, created = Session.objects.get_or_create(
                    restaurant=restaurant,
                    table=res.table,
                    reservation=res,
                    opened_by=waiter,
                    defaults={
                        "guest_count": res.guest_count,
                        "status": SessionStatus.OPEN,
                        "currency": "UAH",
                        "subtotal": 0,
                        "tax": 0,
                        "total": 0,
                        "opened_at": now,
                    },
                )

                sessions_from_res += 1
                profile = next(profiles)
                offset = session_seq
                session_seq += 1

                items_data = (
                    [
                        {"slot": 1, "menu": 0, "qty": 2},
                        {"slot": 1, "menu": 1, "qty": 1},
                        {"slot": 2, "menu": 2, "qty": 1},
                    ]
                    if len(items_pool) >= 3
                    else [
                        {"slot": 1, "menu": 0, "qty": 1},
                    ]
                )

                for idx, data in enumerate(items_data):
                    mi = items_pool[(data["menu"] + offset) % len(items_pool)]
                    unit_price = mi.price
                    total_price = unit_price * data["qty"]

                    order = get_or_create_order(
                        restaurant,
                        session,
                        waiter,
                        {
                            "created_by_source": CreatedBySource.STAFF,
                            "source": OrderSource.WAITER_MANUAL,
                            "status": OrderStatus.SUBMITTED,
                            "payment_status": "unpaid",
                            "currency": "UAH",
                            "total_amount": total_price,
                            "tax_total": total_price * 10 // 100,
                            "notes": None,
                        },
                    )

                    ticket, ticket_created = Ticket.objects.get_or_create(
                        restaurant=restaurant,
                        session=session,
                        order=order,
                        defaults=ticket_defaults_from_profile(profile, now),
                    )
                    if not ticket_created:
                        apply_ticket_profile(ticket, profile, now)

                    item_comment = "No onions" if profile["items"] == "mixed" and idx == 1 else None
                    item, item_created = OrderItem.objects.get_or_create(
                        restaurant=restaurant,
                        order=order,
                        ticket=ticket,
                        menu_item=mi,
                        guest_slot=data["slot"],
                        defaults={
                            "quantity": data["qty"],
                            "status": item_status_from_profile(profile, idx),
                            "comment": item_comment,
                            "unit_price": unit_price,
                            "total_price": total_price,
                            "tax_rate": 0.1,
                            "tax_amount": total_price * 10 // 100,
                        },
                    )
                    if not item_created:
                        item.status = item_status_from_profile(profile, idx)
                        item.comment = item_comment
                        item.save(update_fields=["status", "comment"])

                session.subtotal = (
                    Order.objects.filter(session=session).aggregate(total=models.Sum("total_amount"))["total"] or 0
                )
                session.tax = session.subtotal * 10 // 100
                session.total = session.subtotal + session.tax
                session.save(update_fields=["subtotal", "tax", "total"])

            self.stdout.write(f"  Created {sessions_from_res} session(s) from active reservations.")

            # Create walk-in sessions on free tables (no open sessions AND no active/pending reservations)
            tables_with_reservations = set(
                Reservation.objects.filter(
                    restaurant=restaurant,
                    status__in=[ReservationStatus.PENDING, ReservationStatus.ACTIVE],
                ).values_list("table_id", flat=True)
            )
            free_tables = list(
                Table.objects.filter(restaurant=restaurant, active=True)
                .exclude(
                    id__in=Session.objects.filter(restaurant=restaurant, status=SessionStatus.OPEN).values("table_id")
                )
                .exclude(id__in=tables_with_reservations)
            )[:WALKIN_SESSION_COUNT]

            for free_table in free_tables:
                if not menu_items:
                    continue

                walk_in_reservation = Reservation.objects.create(
                    restaurant=restaurant,
                    table=free_table,
                    guest_count=3,
                    start_at=now - timedelta(minutes=45),
                    end_at=now + timedelta(hours=2),
                    type=ReservationType.WALK_IN,
                    status=ReservationStatus.ACTIVE,
                    created_by_staff=True,
                    customer=None,
                    notes=None,
                )

                session, created = Session.objects.get_or_create(
                    restaurant=restaurant,
                    table=free_table,
                    reservation=walk_in_reservation,
                    opened_by=waiter,
                    defaults={
                        "guest_count": 3,
                        "status": SessionStatus.OPEN,
                        "currency": "UAH",
                        "subtotal": 0,
                        "tax": 0,
                        "total": 0,
                        "opened_at": now - timedelta(minutes=45),
                    },
                )
                if session.ends_at != walk_in_reservation.end_at:
                    session.ends_at = walk_in_reservation.end_at
                    session.save(update_fields=["ends_at"])

                if menu_items:
                    profile = next(profiles)
                    mi = items_pool[session_seq % len(items_pool)]
                    session_seq += 1
                    order = get_or_create_order(
                        restaurant,
                        session,
                        waiter,
                        {
                            "created_by_source": CreatedBySource.STAFF,
                            "source": OrderSource.WAITER_MANUAL,
                            "status": OrderStatus.SUBMITTED,
                            "payment_status": "unpaid",
                            "currency": "UAH",
                            "total_amount": mi.price,
                            "tax_total": mi.price * 10 // 100,
                        },
                    )
                    ticket, ticket_created = Ticket.objects.get_or_create(
                        restaurant=restaurant,
                        session=session,
                        order=order,
                        defaults=ticket_defaults_from_profile(profile, now),
                    )
                    if not ticket_created:
                        apply_ticket_profile(ticket, profile, now)

                    item, item_created = OrderItem.objects.get_or_create(
                        restaurant=restaurant,
                        order=order,
                        ticket=ticket,
                        menu_item=mi,
                        guest_slot=1,
                        defaults={
                            "quantity": 2,
                            "status": item_status_from_profile(profile, 0),
                            "unit_price": mi.price,
                            "total_price": mi.price * 2,
                            "tax_rate": 0.1,
                            "tax_amount": mi.price * 2 * 10 // 100,
                        },
                    )
                    if not item_created:
                        item.status = item_status_from_profile(profile, 0)
                        item.save(update_fields=["status"])
                    session.subtotal = mi.price * 2
                    session.tax = session.subtotal * 10 // 100
                    session.total = session.subtotal + session.tax
                    session.save(update_fields=["subtotal", "tax", "total"])
                    self.stdout.write(f"  Walk-in session on Table {free_table.public_number}.")


def ticket_defaults_from_profile(profile: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Build Ticket field defaults (status + timestamps) from a demo profile."""
    status = profile["status"]
    started_at = None
    completed_at = None
    if status in (TicketStatus.ACTIVE, TicketStatus.COMPLETED):
        started_at = now - timedelta(minutes=profile["started_min"])
    if status == TicketStatus.COMPLETED and started_at is not None:
        completed_at = started_at + timedelta(minutes=profile["prep_min"])
    return {
        "status": status,
        "injected_at": now - timedelta(minutes=profile["injected_min"]),
        "started_at": started_at,
        "completed_at": completed_at,
    }


def get_or_create_order(restaurant: Restaurant, session: Session, waiter: User, defaults: dict[str, Any]) -> Order:
    """Reuse an existing order for the session if present (tolerating demo-data duplicates)."""
    existing = Order.objects.filter(restaurant=restaurant, session=session, created_by=waiter).first()
    if existing is not None:
        return existing
    return Order.objects.create(restaurant=restaurant, session=session, created_by=waiter, **defaults)


def apply_ticket_profile(ticket: Ticket, profile: dict[str, Any], now: datetime) -> None:
    """Refresh an existing demo ticket's status/timestamps so re-seeding repopulates the board."""
    for field, value in ticket_defaults_from_profile(profile, now).items():
        setattr(ticket, field, value)
    ticket.save(update_fields=["status", "injected_at", "started_at", "completed_at"])


def item_status_from_profile(profile: dict[str, Any], index: int) -> str:
    """Per-item status: all ready, all pending, or alternating (first ready)."""
    mode = profile["items"]
    if mode == "all_ready":
        return OrderItemStatus.READY
    if mode == "all_pending":
        return OrderItemStatus.PENDING
    return OrderItemStatus.READY if index % 2 == 0 else OrderItemStatus.PENDING
