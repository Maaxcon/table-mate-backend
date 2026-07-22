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
    {
        "name": "Смак Дому",
        "address": "вул. Хрещатик, 22, Київ, 01001",
        "timezone": "Europe/Kyiv",
        "currency": "UAH",
        "locale": "uk",
        "zones": [
            {"name": "Зал", "sort_order": 0, "canvas_cols": 24, "canvas_rows": 18},
            {"name": "Літня тераса", "sort_order": 1, "canvas_cols": 20, "canvas_rows": 14},
        ],
        "tables": [
            {"public_number": "1", "capacity": 2, "zone_name": "Зал"},
            {"public_number": "2", "capacity": 2, "zone_name": "Зал"},
            {"public_number": "3", "capacity": 4, "zone_name": "Зал"},
            {"public_number": "4", "capacity": 4, "zone_name": "Зал"},
            {"public_number": "5", "capacity": 6, "zone_name": "Зал"},
            {"public_number": "6", "capacity": 8, "zone_name": "Зал"},
            {"public_number": "7", "capacity": 10, "zone_name": "Зал"},
            {"public_number": "В1", "capacity": 2, "zone_name": "Літня тераса"},
            {"public_number": "В2", "capacity": 2, "zone_name": "Літня тераса"},
            {"public_number": "В3", "capacity": 4, "zone_name": "Літня тераса"},
            {"public_number": "В4", "capacity": 4, "zone_name": "Літня тераса"},
        ],
    },
    {
        "name": "Барва",
        "address": "просп. Перемоги, 45, Київ, 03150",
        "timezone": "Europe/Kyiv",
        "currency": "UAH",
        "locale": "uk",
        "zones": [
            {"name": "Основний зал", "sort_order": 0, "canvas_cols": 28, "canvas_rows": 20},
            {"name": "Барна зона", "sort_order": 1, "canvas_cols": 16, "canvas_rows": 12},
            {"private": True, "name": "VIP-кімната", "sort_order": 2, "canvas_cols": 10, "canvas_rows": 8},
        ],
        "tables": [
            {"public_number": "A1", "capacity": 2, "zone_name": "Основний зал"},
            {"public_number": "A2", "capacity": 2, "zone_name": "Основний зал"},
            {"public_number": "A3", "capacity": 4, "zone_name": "Основний зал"},
            {"public_number": "A4", "capacity": 4, "zone_name": "Основний зал"},
            {"public_number": "A5", "capacity": 6, "zone_name": "Основний зал"},
            {"public_number": "A6", "capacity": 6, "zone_name": "Основний зал"},
            {"public_number": "A7", "capacity": 8, "zone_name": "Основний зал"},
            {"public_number": "Б1", "capacity": 2, "zone_name": "Барна зона"},
            {"public_number": "Б2", "capacity": 2, "zone_name": "Барна зона"},
            {"public_number": "Б3", "capacity": 2, "zone_name": "Барна зона"},
            {"public_number": "Б4", "capacity": 4, "zone_name": "Барна зона"},
            {"public_number": "V1", "capacity": 12, "zone_name": "VIP-кімната"},
        ],
    },
    {
        "name": "Козацький Двір",
        "address": "вул. Соборна, 31, Одеса, 65000",
        "timezone": "Europe/Kyiv",
        "currency": "UAH",
        "locale": "uk",
        "zones": [
            {"name": "Великий зал", "sort_order": 0, "canvas_cols": 30, "canvas_rows": 22},
            {"name": "Козацька хата", "sort_order": 1, "canvas_cols": 18, "canvas_rows": 14},
            {"name": "Двір", "sort_order": 2, "canvas_cols": 22, "canvas_rows": 16},
        ],
        "tables": [
            {"public_number": "К1", "capacity": 4, "zone_name": "Великий зал"},
            {"public_number": "К2", "capacity": 4, "zone_name": "Великий зал"},
            {"public_number": "К3", "capacity": 6, "zone_name": "Великий зал"},
            {"public_number": "К4", "capacity": 6, "zone_name": "Великий зал"},
            {"public_number": "К5", "capacity": 8, "zone_name": "Великий зал"},
            {"public_number": "К6", "capacity": 10, "zone_name": "Великий зал"},
            {"public_number": "К7", "capacity": 12, "zone_name": "Великий зал"},
            {"public_number": "Х1", "capacity": 2, "zone_name": "Козацька хата"},
            {"public_number": "Х2", "capacity": 4, "zone_name": "Козацька хата"},
            {"public_number": "Х3", "capacity": 6, "zone_name": "Козацька хата"},
            {"public_number": "Д1", "capacity": 4, "zone_name": "Двір"},
            {"public_number": "Д2", "capacity": 4, "zone_name": "Двір"},
            {"public_number": "Д3", "capacity": 6, "zone_name": "Двір"},
            {"public_number": "Д4", "capacity": 8, "zone_name": "Двір"},
            {"public_number": "Д5", "capacity": 10, "zone_name": "Двір"},
        ],
    },
    {
        "name": "Море Смаку",
        "address": "наб. Рибальська, 7, Харків, 61000",
        "timezone": "Europe/Kyiv",
        "currency": "UAH",
        "locale": "uk",
        "zones": [
            {"name": "Головний зал", "sort_order": 0, "canvas_cols": 26, "canvas_rows": 20},
            {"name": "Тераса біля води", "sort_order": 1, "canvas_cols": 24, "canvas_rows": 16},
        ],
        "tables": [
            {"public_number": "M1", "capacity": 2, "zone_name": "Головний зал"},
            {"public_number": "M2", "capacity": 2, "zone_name": "Головний зал"},
            {"public_number": "M3", "capacity": 4, "zone_name": "Головний зал"},
            {"public_number": "M4", "capacity": 4, "zone_name": "Головний зал"},
            {"public_number": "M5", "capacity": 6, "zone_name": "Головний зал"},
            {"public_number": "M6", "capacity": 8, "zone_name": "Головний зал"},
            {"public_number": "T1", "capacity": 2, "zone_name": "Тераса біля води"},
            {"public_number": "T2", "capacity": 2, "zone_name": "Тераса біля води"},
            {"public_number": "T3", "capacity": 4, "zone_name": "Тераса біля води"},
            {"public_number": "T4", "capacity": 4, "zone_name": "Тераса біля води"},
            {"public_number": "T5", "capacity": 6, "zone_name": "Тераса біля води"},
        ],
    },
    {
        "name": "Вогнище",
        "address": "вул. Дерибасівська, 10, Одеса, 65000",
        "timezone": "Europe/Kyiv",
        "currency": "UAH",
        "locale": "uk",
        "zones": [
            {"name": "Зал біля каміну", "sort_order": 0, "canvas_cols": 22, "canvas_rows": 16},
            {"name": "Основний зал", "sort_order": 1, "canvas_cols": 28, "canvas_rows": 20},
            {"name": "Відкрита кухня", "sort_order": 2, "canvas_cols": 14, "canvas_rows": 12},
        ],
        "tables": [
            {"public_number": "В1", "capacity": 2, "zone_name": "Зал біля каміну"},
            {"public_number": "В2", "capacity": 2, "zone_name": "Зал біля каміну"},
            {"public_number": "В3", "capacity": 4, "zone_name": "Зал біля каміну"},
            {"public_number": "О1", "capacity": 2, "zone_name": "Основний зал"},
            {"public_number": "О2", "capacity": 4, "zone_name": "Основний зал"},
            {"public_number": "О3", "capacity": 4, "zone_name": "Основний зал"},
            {"public_number": "О4", "capacity": 6, "zone_name": "Основний зал"},
            {"public_number": "О5", "capacity": 6, "zone_name": "Основний зал"},
            {"public_number": "О6", "capacity": 8, "zone_name": "Основний зал"},
            {"public_number": "О7", "capacity": 10, "zone_name": "Основний зал"},
            {"public_number": "К1", "capacity": 4, "zone_name": "Відкрита кухня"},
            {"public_number": "К2", "capacity": 6, "zone_name": "Відкрита кухня"},
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
                self._prune_zones(restaurant, {str(z["name"]) for z in data["zones"]})

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
