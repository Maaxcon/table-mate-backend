from typing import Any, TypedDict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.restaurants.models import Restaurant, RestaurantSettings, Table, Zone


class _TableData(TypedDict):
    public_number: str
    capacity: int
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
        "name": "UniTable",
        "address": "пров. Січовий 17, Черкаси, 18015",
        "timezone": "Europe/Kyiv",
        "currency": "UAH",
        "locale": "uk",
        "zones": [
            {"name": "Main Hall", "sort_order": 0, "canvas_cols": 30, "canvas_rows": 18},
            {"name": "Open Space", "sort_order": 1, "canvas_cols": 34, "canvas_rows": 27},
            {"name": "Roof", "sort_order": 2, "canvas_cols": 28, "canvas_rows": 20},
        ],
        "tables": [
            {"public_number": "kathe", "capacity": 1, "zone_name": "Main Hall"},
            {"public_number": "marie", "capacity": 1, "zone_name": "Main Hall"},
            {"public_number": "mini", "capacity": 2, "zone_name": "Main Hall"},
            {"public_number": "T1", "capacity": 3, "zone_name": "Main Hall"},
            {"public_number": "T1.5", "capacity": 3, "zone_name": "Main Hall"},
            {"public_number": "переговорка", "capacity": 8, "zone_name": "Main Hall"},
            {"public_number": "T2", "capacity": 4, "zone_name": "Open Space"},
            {"public_number": "T3", "capacity": 4, "zone_name": "Open Space"},
            {"public_number": "T4", "capacity": 6, "zone_name": "Open Space"},
            {"public_number": "T5", "capacity": 6, "zone_name": "Open Space"},
            {"public_number": "T6", "capacity": 4, "zone_name": "Open Space"},
            {"public_number": "T6.5", "capacity": 4, "zone_name": "Open Space"},
            {"public_number": "T7", "capacity": 4, "zone_name": "Roof"},
            {"public_number": "T8", "capacity": 4, "zone_name": "Roof"},
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
            {"public_number": "T1", "capacity": 2, "zone_name": "Indoor"},
            {"public_number": "T2", "capacity": 2, "zone_name": "Indoor"},
            {"public_number": "T3", "capacity": 4, "zone_name": "Indoor"},
            {"public_number": "T4", "capacity": 4, "zone_name": "Terrace"},
            {"public_number": "T5", "capacity": 6, "zone_name": "Terrace"},
        ],
    },
]

DEFAULT_WORKING_HOURS: dict[str, dict[str, str]] = {
    "mon": {"open": "10:00", "close": "23:00"},
    "tue": {"open": "10:00", "close": "23:00"},
    "wed": {"open": "10:00", "close": "23:00"},
    "thu": {"open": "10:00", "close": "23:00"},
    "fri": {"open": "10:00", "close": "00:00"},
    "sat": {"open": "10:00", "close": "00:00"},
    "sun": {"open": "11:00", "close": "22:00"},
}


class Command(BaseCommand):
    help = "Seed restaurants, settings, and tables"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--restaurant-id",
            type=int,
            help="Restaurant ID to seed (seeds all if omitted)",
        )
        parser.add_argument(
            "--prune",
            action="store_true",
            help="Delete tables (and their sessions/reservations) whose public_number "
            "is not in the canonical seed set for the restaurant.",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        created_restaurants = 0
        created_settings = 0
        created_zones = 0
        created_tables = 0
        pruned_tables = 0

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
            settings.full_clean()  # catch invalid working_hours keys instead of seeding bad data
            if was_created_settings:
                created_settings += 1

            zone_map: dict[str, Zone] = {}
            for zone_data in data["zones"]:
                zone_obj, was_created_zone = Zone.objects.update_or_create(
                    restaurant=restaurant,
                    name=str(zone_data["name"]),
                    defaults={
                        "sort_order": int(zone_data["sort_order"]),
                        "canvas_cols": int(zone_data.get("canvas_cols", 20)),
                        "canvas_rows": int(zone_data.get("canvas_rows", 20)),
                    },
                )
                zone_map[zone_obj.name] = zone_obj
                if was_created_zone:
                    created_zones += 1

            canonical_numbers = {t["public_number"] for t in data["tables"]}
            for table_data in data["tables"]:
                zone = zone_map.get(str(table_data["zone_name"]))
                if zone is None:
                    raise CommandError(
                        f"Table {table_data['public_number']!r} references unknown zone "
                        f"{table_data['zone_name']!r}."
                    )
                _, was_created_table = Table.objects.update_or_create(
                    restaurant=restaurant,
                    public_number=table_data["public_number"],
                    defaults={
                        "capacity": table_data["capacity"],
                        "active": True,
                        "zone": zone,
                    },
                )
                if was_created_table:
                    created_tables += 1

            if options["prune"]:
                pruned_tables += self._prune_tables(restaurant, canonical_numbers)
                self._prune_zones(restaurant, {z["name"] for z in data["zones"]})

            if options["restaurant_id"]:
                break

        summary = (
            f"Done: {created_restaurants} restaurants, "
            f"{created_settings} settings, {created_zones} zones, "
            f"{created_tables} tables"
        )
        if options["prune"]:
            summary += f", {pruned_tables} tables pruned"
        self.stdout.write(self.style.SUCCESS(summary))

    def _prune_tables(self, restaurant: Restaurant, canonical_numbers: set[str]) -> int:
        """Delete tables not in the canonical seed set, plus their dependents.

        Session.table is on_delete=PROTECT (and Session.reservation too), so the
        sessions and reservations have to go first; deleting them cascades their
        orders, tickets, order items and cart sessions.
        """
        from apps.orders.models import Session
        from apps.reservations.models import Reservation

        orphans = list(
            Table.objects.filter(restaurant=restaurant).exclude(public_number__in=canonical_numbers)
        )
        if not orphans:
            return 0

        orphan_numbers = sorted(t.public_number for t in orphans)
        orphan_ids = [t.id for t in orphans]
        Session.objects.filter(restaurant=restaurant, table_id__in=orphan_ids).delete()
        Reservation.objects.filter(restaurant=restaurant, table_id__in=orphan_ids).delete()
        deleted, _ = Table.objects.filter(id__in=orphan_ids).delete()

        self.stdout.write(
            self.style.WARNING(f"  Pruned {len(orphans)} orphaned table(s): {', '.join(orphan_numbers)}")
        )
        return len(orphans)

    def _prune_zones(self, restaurant: Restaurant, canonical_zone_names: set[str]) -> None:
        from apps.restaurants.models import Zone

        orphan_zones = Zone.objects.filter(restaurant=restaurant).exclude(name__in=canonical_zone_names)
        if not orphan_zones.exists():
            return

        zone_names = list(orphan_zones.values_list("name", flat=True))
        orphan_zones.delete()
        self.stdout.write(
            self.style.WARNING(f"  Pruned orphaned zone(s): {', '.join(zone_names)}")
        )
