from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.authentication.models import RoleCode, User
from apps.receipts.models import PaymentMethod, Receipt, ReceiptItem
from apps.restaurants.models import Restaurant

# The same sample data the frontend used as a mock, now seeded into the DB.
SAMPLE_RECEIPTS: list[dict[str, Any]] = [
    {
        "order_number": "TM-2026-0518-014",
        "visited_at": datetime(2026, 5, 18, 19, 30, tzinfo=UTC),
        "table_label": "Table 7",
        "server_name": "Olena K.",
        "guests": 3,
        "tax": "4.25",
        "service_charge": "4.25",
        "tip": "6.00",
        "payment_method": PaymentMethod.CARD,
        "items": [
            ("Ribeye steak", 1, "24.50"),
            ("Caesar salad", 1, "9.00"),
            ("Lemonade", 2, "4.50"),
        ],
    },
    {
        "order_number": "TM-2026-0429-008",
        "visited_at": datetime(2026, 4, 29, 13, 5, tzinfo=UTC),
        "table_label": "Table 2",
        "server_name": "Andriy M.",
        "guests": 1,
        "tax": "1.60",
        "service_charge": "1.60",
        "tip": "2.00",
        "payment_method": PaymentMethod.CASH,
        "items": [
            ("Margherita pizza", 1, "13.00"),
            ("Espresso", 1, "3.00"),
        ],
    },
    {
        "order_number": "TM-2026-0311-021",
        "visited_at": datetime(2026, 3, 11, 20, 15, tzinfo=UTC),
        "table_label": "Table 12",
        "server_name": "Olena K.",
        "guests": 4,
        "tax": "5.29",
        "service_charge": "5.29",
        "tip": "7.00",
        "payment_method": PaymentMethod.CARD,
        "items": [
            ("Burger", 2, "12.00"),
            ("Fries", 2, "5.00"),
            ("Craft beer", 3, "6.30"),
        ],
    },
]


class Command(BaseCommand):
    help = "Seed sample cabinet receipts for a customer (the old frontend mock data)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--email", help="Customer email. Defaults to the first customer.")

    def handle(self, *args: Any, **options: Any) -> None:
        email = options.get("email")
        if email:
            user = User.objects.filter(email=email).first()
            if user is None:
                raise CommandError(f"No user with email {email!r}.")
        else:
            user = User.objects.filter(role=RoleCode.CUSTOMER).order_by("id").first()
            if user is None:
                raise CommandError("No customer users found. Pass --email.")

        restaurant, _ = Restaurant.objects.get_or_create(
            name="TableMate Bistro",
            defaults={
                "address": "12 Khreshchatyk St, Kyiv, 01001",
                "phone": "+380 44 123 45 67",
            },
        )

        created = 0
        for data in SAMPLE_RECEIPTS:
            if Receipt.objects.filter(customer=user, order_number=data["order_number"]).exists():
                self.stdout.write(f"skip {data['order_number']} (already exists)")
                continue
            receipt = Receipt.objects.create(
                customer=user,
                restaurant=restaurant,
                order_number=data["order_number"],
                visited_at=data["visited_at"],
                currency="USD",
                table_label=data["table_label"],
                server_name=data["server_name"],
                guests=data["guests"],
                tax=Decimal(data["tax"]),
                service_charge=Decimal(data["service_charge"]),
                tip=Decimal(data["tip"]),
                payment_method=data["payment_method"],
            )
            for name, qty, price in data["items"]:
                ReceiptItem.objects.create(
                    receipt=receipt,
                    name=name,
                    quantity=qty,
                    unit_price=Decimal(price),
                )
            created += 1
            self.stdout.write(self.style.SUCCESS(f"created {data['order_number']}"))

        self.stdout.write(
            self.style.SUCCESS(f"Done. {created} receipt(s) created for {user.email}.")
        )
