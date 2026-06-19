from __future__ import annotations

import uuid
from argparse import ArgumentParser

from django.core.management.base import BaseCommand

from common.notification_events import (
    emit_cart_checked_out,
    emit_cart_created,
    emit_hall_new_reservation_notification,
    emit_kitchen_ticket_injected,
    emit_order_item_status_changed,
)


class Command(BaseCommand):
    help = "Broadcast a test WebSocket notification to staff of a given restaurant"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("restaurant_id", type=int, help="Restaurant ID to broadcast to")
        parser.add_argument(
            "--type",
            default="cart_created",
            choices=[
                "cart_created",
                "cart_checked_out",
                "hall_new_reservation",
                "kitchen_ticket_injected",
                "order_item_status_changed",
            ],
            help="Notification type to broadcast",
        )

    def handle(self, *args: str, **options: str | int) -> None:
        rid = int(options["restaurant_id"])
        kind = str(options["type"])

        events = {
            "cart_created": lambda: emit_cart_created(
                rid, session_id=str(uuid.uuid4()), table_number="5", guest_name="Test Guest"
            ),
            "cart_checked_out": lambda: emit_cart_checked_out(
                rid, session_id=str(uuid.uuid4()), table_number="5", guest_name="Test Guest"
            ),
            "hall_new_reservation": lambda: emit_hall_new_reservation_notification(
                rid,
                reservation_id=str(uuid.uuid4()),
                table_number="5",
                guest_name="Test Guest",
                guest_count=4,
            ),
            "kitchen_ticket_injected": lambda: emit_kitchen_ticket_injected(
                rid, ticket_id=str(uuid.uuid4()), table_number="5", items_count=3
            ),
            "order_item_status_changed": lambda: emit_order_item_status_changed(
                rid, order_item_id=str(uuid.uuid4()), table_number="5", menu_item_name="Burger", status="ready"
            ),
        }

        events[kind]()
        self.stdout.write(self.style.SUCCESS(f"Sent {kind} notification to restaurant {rid}"))
