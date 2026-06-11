from typing import Any, TypedDict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.restaurants.models import Restaurant, RestaurantSettings, Table, TableShape, Zone


class _TableData(TypedDict):
    table_number: str
    capacity: int
    shape: str
    position_x: int
    position_y: int
    zone_name: str


class _RestaurantData(TypedDict):
    name: str
    address: str
    timezone: str
    currency: str
    locale: str
    zones: list[dict[str, str | int]]
    tables: list[_TableData]


_RESTAURANTS_DATA: list[_RestaurantData] = [
    {
        "name": "Table Mate",
        "address": "вул. Хрещатик, 1, Київ, 01001",
        "timezone": "Europe/Kyiv",
        "currency": "UAH",
        "locale": "uk",
        "zones": [
            {"name": "Main Hall", "sort_order": 0},
            {"name": "VIP Room", "sort_order": 1},
            {"name": "Winter Garden", "sort_order": 2},
        ],
        "tables": [
            {
                "table_number": "1",
                "capacity": 2,
                "shape": TableShape.ROUND,
                "position_x": 50,
                "position_y": 100,
                "zone_name": "Main Hall",
            },
            {
                "table_number": "2",
                "capacity": 2,
                "shape": TableShape.ROUND,
                "position_x": 50,
                "position_y": 200,
                "zone_name": "Main Hall",
            },
            {
                "table_number": "3",
                "capacity": 4,
                "shape": TableShape.RECTANGLE,
                "position_x": 150,
                "position_y": 100,
                "zone_name": "Main Hall",
            },
            {
                "table_number": "4",
                "capacity": 4,
                "shape": TableShape.RECTANGLE,
                "position_x": 150,
                "position_y": 200,
                "zone_name": "Main Hall",
            },
            {
                "table_number": "5",
                "capacity": 4,
                "shape": TableShape.RECTANGLE,
                "position_x": 150,
                "position_y": 300,
                "zone_name": "Main Hall",
            },
            {
                "table_number": "6",
                "capacity": 6,
                "shape": TableShape.SQUARE,
                "position_x": 300,
                "position_y": 150,
                "zone_name": "VIP Room",
            },
            {
                "table_number": "7",
                "capacity": 6,
                "shape": TableShape.SQUARE,
                "position_x": 300,
                "position_y": 300,
                "zone_name": "VIP Room",
            },
            {
                "table_number": "8",
                "capacity": 8,
                "shape": TableShape.RECTANGLE,
                "position_x": 450,
                "position_y": 100,
                "zone_name": "Winter Garden",
            },
            {
                "table_number": "9",
                "capacity": 4,
                "shape": TableShape.BOOTH,
                "position_x": 450,
                "position_y": 250,
                "zone_name": "Winter Garden",
            },
            {
                "table_number": "10",
                "capacity": 4,
                "shape": TableShape.BOOTH,
                "position_x": 450,
                "position_y": 350,
                "zone_name": "Winter Garden",
            },
        ],
    },
    {
        "name": "Table Mate Terrace",
        "address": "вул. Михайлівська, 12, Київ, 01001",
        "timezone": "Europe/Kyiv",
        "currency": "UAH",
        "locale": "uk",
        "zones": [
            {"name": "Indoor", "sort_order": 0},
            {"name": "Terrace", "sort_order": 1},
        ],
        "tables": [
            {
                "table_number": "T1",
                "capacity": 2,
                "shape": TableShape.ROUND,
                "position_x": 40,
                "position_y": 80,
                "zone_name": "Indoor",
            },
            {
                "table_number": "T2",
                "capacity": 2,
                "shape": TableShape.ROUND,
                "position_x": 40,
                "position_y": 180,
                "zone_name": "Indoor",
            },
            {
                "table_number": "T3",
                "capacity": 4,
                "shape": TableShape.RECTANGLE,
                "position_x": 120,
                "position_y": 80,
                "zone_name": "Indoor",
            },
            {
                "table_number": "T4",
                "capacity": 4,
                "shape": TableShape.RECTANGLE,
                "position_x": 120,
                "position_y": 200,
                "zone_name": "Terrace",
            },
            {
                "table_number": "T5",
                "capacity": 6,
                "shape": TableShape.SQUARE,
                "position_x": 250,
                "position_y": 120,
                "zone_name": "Terrace",
            },
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
        created_zones = 0
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

            self.stdout.write(f"Seeding zones and tables for restaurant: {restaurant.name}")

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

            zone_map: dict[str, Zone] = {}
            for zone_data in data["zones"]:
                zone_obj, was_created_zone = Zone.objects.update_or_create(
                    restaurant=restaurant,
                    name=str(zone_data["name"]),
                    defaults={"sort_order": int(zone_data["sort_order"])},
                )
                zone_map[zone_obj.name] = zone_obj
                if was_created_zone:
                    created_zones += 1

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
                        "zone": zone_map.get(str(table_data["zone_name"])),
                    },
                )
                if was_created_table:
                    created_tables += 1

            if options["restaurant_id"]:
                break

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {created_restaurants} restaurants, "
                f"{created_settings} settings, {created_zones} zones, "
                f"{created_tables} tables"
            )
        )
