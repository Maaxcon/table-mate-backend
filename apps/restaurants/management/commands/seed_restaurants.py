from typing import Any, TypedDict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.restaurants.models import Restaurant, RestaurantSettings, Table, TableShape


class _TableData(TypedDict):
    table_number: str
    capacity: int
    shape: str
    position_x: int
    position_y: int


class _RestaurantData(TypedDict):
    name: str
    address: str
    timezone: str
    currency: str
    locale: str
    tables: list[_TableData]


_RESTAURANTS_DATA: list[_RestaurantData] = [
    {
        "name": "Table Mate",
        "address": "вул. Хрещатик, 1, Київ, 01001",
        "timezone": "Europe/Kyiv",
        "currency": "UAH",
        "locale": "uk",
        "tables": [
            {"table_number": "1", "capacity": 2, "shape": TableShape.ROUND, "position_x": 50, "position_y": 100},
            {"table_number": "2", "capacity": 2, "shape": TableShape.ROUND, "position_x": 50, "position_y": 200},
            {"table_number": "3", "capacity": 4, "shape": TableShape.RECTANGLE, "position_x": 150, "position_y": 100},
            {"table_number": "4", "capacity": 4, "shape": TableShape.RECTANGLE, "position_x": 150, "position_y": 200},
            {"table_number": "5", "capacity": 4, "shape": TableShape.RECTANGLE, "position_x": 150, "position_y": 300},
            {"table_number": "6", "capacity": 6, "shape": TableShape.SQUARE, "position_x": 300, "position_y": 150},
            {"table_number": "7", "capacity": 6, "shape": TableShape.SQUARE, "position_x": 300, "position_y": 300},
            {"table_number": "8", "capacity": 8, "shape": TableShape.RECTANGLE, "position_x": 450, "position_y": 100},
            {"table_number": "9", "capacity": 4, "shape": TableShape.BOOTH, "position_x": 450, "position_y": 250},
            {"table_number": "10", "capacity": 4, "shape": TableShape.BOOTH, "position_x": 450, "position_y": 350},
        ],
    },
    {
        "name": "Table Mate Terrace",
        "address": "вул. Михайлівська, 12, Київ, 01001",
        "timezone": "Europe/Kyiv",
        "currency": "UAH",
        "locale": "uk",
        "tables": [
            {"table_number": "T1", "capacity": 2, "shape": TableShape.ROUND, "position_x": 40, "position_y": 80},
            {"table_number": "T2", "capacity": 2, "shape": TableShape.ROUND, "position_x": 40, "position_y": 180},
            {"table_number": "T3", "capacity": 4, "shape": TableShape.RECTANGLE, "position_x": 120, "position_y": 80},
            {"table_number": "T4", "capacity": 4, "shape": TableShape.RECTANGLE, "position_x": 120, "position_y": 200},
            {"table_number": "T5", "capacity": 6, "shape": TableShape.SQUARE, "position_x": 250, "position_y": 120},
        ],
    },
]

DEFAULT_WORKING_HOURS: dict[str, dict[str, str]] = {
    "monday": {"open": "10:00", "close": "23:00"},
    "tuesday": {"open": "10:00", "close": "23:00"},
    "wednesday": {"open": "10:00", "close": "23:00"},
    "thursday": {"open": "10:00", "close": "23:00"},
    "friday": {"open": "10:00", "close": "00:00"},
    "saturday": {"open": "10:00", "close": "00:00"},
    "sunday": {"open": "11:00", "close": "22:00"},
}


class Command(BaseCommand):
    help = "Seed restaurants, settings, and tables"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--restaurant-id",
            type=int,
            help="Restaurant ID to seed (seeds all if omitted)",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        created_restaurants = 0
        created_settings = 0
        created_tables = 0

        for data in _RESTAURANTS_DATA:
            if options["restaurant_id"]:
                try:
                    restaurant = Restaurant.objects.get(pk=options["restaurant_id"])
                except Restaurant.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"Restaurant {options['restaurant_id']} not found."))
                    return
            else:
                restaurant, was_created = Restaurant.objects.update_or_create(
                    name=data["name"],
                    defaults={"address": data["address"]},
                )
                if was_created:
                    created_restaurants += 1

            self.stdout.write(f"Seeding tables for restaurant: {restaurant.name}")

            settings, was_created_settings = RestaurantSettings.objects.update_or_create(
                restaurant=restaurant,
                defaults={
                    "timezone": data["timezone"],
                    "currency": data["currency"],
                    "locale": data["locale"],
                    "working_hours": DEFAULT_WORKING_HOURS,
                },
            )
            if was_created_settings:
                created_settings += 1

            for table_data in data["tables"]:
                _, was_created_table = Table.objects.update_or_create(
                    restaurant=restaurant,
                    table_number=table_data["table_number"],
                    defaults={
                        "capacity": table_data["capacity"],
                        "shape": table_data["shape"],
                        "position_x": table_data["position_x"],
                        "position_y": table_data["position_y"],
                        "active": True,
                    },
                )
                if was_created_table:
                    created_tables += 1

            if options["restaurant_id"]:
                break

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {created_restaurants} restaurants, {created_settings} settings, {created_tables} tables"
            )
        )
