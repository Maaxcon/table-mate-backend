from datetime import timedelta
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
from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import Restaurant, Table, TableStatus

WALKIN_SESSION_COUNT = 3


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

            menu_items = list(MenuItem.objects.filter(restaurant=restaurant).order_by("id"))
            if not menu_items:
                self.stdout.write(self.style.WARNING(f"No menu items for {restaurant.name}. Skipping."))

            active_reservations = list(
                Reservation.objects.filter(
                    restaurant=restaurant,
                    start_at__lte=now,
                    end_at__gt=now,
                    status__in=[ReservationStatus.PENDING, ReservationStatus.ACTIVE],
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
                        "running_total": 0,
                        "final_total": 0,
                        "started_at": res.start_at,
                    },
                )
                if not created:
                    continue

                sessions_from_res += 1

                # Mark the table as occupied on the floor plan
                if res.table.status != TableStatus.OCCUPIED:
                    res.table.status = TableStatus.OCCUPIED
                    res.table.save(update_fields=["status"])

                items_data = (
                    [
                        {"slot": 1, "menu": 0, "qty": 2},
                        {"slot": 1, "menu": 1, "qty": 1},
                        {"slot": 2, "menu": 2, "qty": 1},
                    ]
                    if len(menu_items) >= 3
                    else [
                        {"slot": 1, "menu": 0, "qty": 1},
                    ]
                )

                for data in items_data:
                    mi = menu_items[data["menu"] % len(menu_items)]
                    unit_price = mi.price
                    total_price = unit_price * data["qty"]

                    order, _ = Order.objects.get_or_create(
                        restaurant=restaurant,
                        session=session,
                        created_by=waiter,
                        defaults={
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

                    ticket, _ = Ticket.objects.get_or_create(
                        restaurant=restaurant,
                        session=session,
                        order=order,
                        defaults={
                            "status": TicketStatus.ACTIVE,
                            "injected_at": now,
                            "started_at": now,
                        },
                    )

                    OrderItem.objects.get_or_create(
                        restaurant=restaurant,
                        order=order,
                        ticket=ticket,
                        menu_item=mi,
                        guest_slot=data["slot"],
                        defaults={
                            "quantity": data["qty"],
                            "status": random_item_status(),
                            "unit_price": unit_price,
                            "total_price": total_price,
                            "tax_rate": 0.1,
                            "tax_amount": total_price * 10 // 100,
                        },
                    )

                session.running_total = (
                    Order.objects.filter(session=session).aggregate(total=models.Sum("total_amount"))["total"] or 0
                )
                session.save(update_fields=["running_total"])

            self.stdout.write(f"  Created {sessions_from_res} session(s) from active reservations.")

            # Create walk-in sessions on free tables
            free_tables = list(
                Table.objects.filter(restaurant=restaurant, active=True)
                .exclude(
                    id__in=Session.objects.filter(restaurant=restaurant, status=SessionStatus.OPEN).values("table_id")
                )
                .exclude(id__in=[r.table_id for r in active_reservations if r.table_id])
            )[:WALKIN_SESSION_COUNT]

            for free_table in free_tables:
                if not menu_items:
                    continue

                session, created = Session.objects.get_or_create(
                    restaurant=restaurant,
                    table=free_table,
                    opened_by=waiter,
                    defaults={
                        "guest_count": 3,
                        "status": SessionStatus.OPEN,
                        "currency": "UAH",
                        "running_total": 0,
                        "final_total": 0,
                        "started_at": now - timedelta(minutes=45),
                    },
                )
                if not created:
                    continue

                # Mark the table as occupied on the floor plan
                if free_table.status != TableStatus.OCCUPIED:
                    free_table.status = TableStatus.OCCUPIED
                    free_table.save(update_fields=["status"])

                if menu_items:
                    mi = menu_items[0]
                    order, _ = Order.objects.get_or_create(
                        restaurant=restaurant,
                        session=session,
                        created_by=waiter,
                        defaults={
                            "created_by_source": CreatedBySource.STAFF,
                            "source": OrderSource.WAITER_MANUAL,
                            "status": OrderStatus.SUBMITTED,
                            "payment_status": "unpaid",
                            "currency": "UAH",
                            "total_amount": mi.price,
                            "tax_total": mi.price * 10 // 100,
                        },
                    )
                    ticket, _ = Ticket.objects.get_or_create(
                        restaurant=restaurant,
                        session=session,
                        order=order,
                        defaults={
                            "status": TicketStatus.ACTIVE,
                            "injected_at": now,
                            "started_at": now - timedelta(minutes=45),
                        },
                    )
                    OrderItem.objects.get_or_create(
                        restaurant=restaurant,
                        order=order,
                        ticket=ticket,
                        menu_item=mi,
                        guest_slot=1,
                        defaults={
                            "quantity": 2,
                            "status": OrderItemStatus.SERVED,
                            "unit_price": mi.price,
                            "total_price": mi.price * 2,
                            "tax_rate": 0.1,
                            "tax_amount": mi.price * 2 * 10 // 100,
                        },
                    )
                    session.running_total = mi.price * 2
                    session.save(update_fields=["running_total"])
                    self.stdout.write(f"  Walk-in session on Table {free_table.table_number}.")


def random_item_status() -> str:
    import random

    return random.choice(  # nosec B311
        [
            OrderItemStatus.PENDING,
            OrderItemStatus.IN_PROGRESS,
            OrderItemStatus.READY,
            OrderItemStatus.SERVED,
        ]
    )
