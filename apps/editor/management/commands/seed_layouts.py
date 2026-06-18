from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.editor.models import LayoutVersion
from apps.restaurants.models import Restaurant, Table, Zone


def _t(
    num: str,
    x: int,
    y: int,
    w: int,
    h: int,
    shape: str,
    cap: int,
    zone: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "public_number": num,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "rotation": 0,
        "shape": shape,
        "capacity": cap,
        "zone_name": zone,
        "tags": tags or [],
    }


def _obs(x: int, y: int, w: int, h: int) -> dict[str, Any]:
    return {"x": x, "y": y, "width": w, "height": h, "rotation": 0}


def _portal(x: int, y: int, w: int, h: int, zone: str, label: str) -> dict[str, Any]:
    return {
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "target_zone_name": zone,
        "label": label,
    }


_LAYOUTS: dict[str, dict[str, Any]] = {
    "Table Mate": {
        "tables": [
            _t("T1", 120, 120, 74, 74, "round", 2, "Main Hall", ["window"]),
            _t("T2", 120, 260, 74, 74, "round", 2, "Main Hall"),
            _t("T3", 260, 120, 120, 120, "square", 4, "Main Hall"),
            _t("T4", 260, 260, 120, 120, "square", 4, "Main Hall", ["quiet"]),
            _t("T5", 260, 400, 120, 120, "square", 4, "Main Hall"),
            _t("T6", 500, 120, 120, 120, "square", 6, "VIP Room"),
            _t("T7", 500, 260, 120, 120, "square", 6, "VIP Room"),
            _t("T8", 740, 120, 180, 120, "rectangle", 8, "Winter Garden", ["window"]),
            _t("T9", 740, 300, 120, 120, "square", 4, "Winter Garden"),
            _t("T10", 740, 440, 120, 120, "square", 4, "Winter Garden"),
        ],
        "obstacles": [
            _obs(0, 0, 1200, 10),
            _obs(0, 600, 1200, 10),
        ],
        "thresholds": [
            {"x": 420, "y": 400, "width": 200, "height": 10},
        ],
        "portals": [
            _portal(900, 400, 120, 120, "VIP Room", "VIP Room"),
        ],
    },
    "Table Mate Terrace": {
        "tables": [
            _t("T1", 120, 120, 74, 74, "round", 2, "Indoor"),
            _t("T2", 120, 260, 74, 74, "round", 2, "Indoor"),
            _t("T3", 260, 120, 120, 120, "square", 4, "Indoor"),
            _t("T4", 500, 120, 120, 120, "square", 4, "Terrace", ["window"]),
            _t("T5", 500, 260, 120, 120, "square", 6, "Terrace"),
        ],
        "obstacles": [
            _obs(0, 0, 800, 10),
        ],
        "thresholds": [],
        "portals": [
            _portal(400, 200, 80, 80, "Terrace", "Terrace"),
        ],
    },
}


class Command(BaseCommand):
    help = "Seed layout JSON data for development"

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

        created_count = 0

        for restaurant in restaurants:
            cfg = _LAYOUTS.get(restaurant.name)
            if not cfg:
                self.stdout.write(
                    self.style.WARNING(f"No layout config for '{restaurant.name}', skipping.")
                )
                continue

            zones = {z.name: z for z in Zone.objects.filter(restaurant=restaurant)}
            tables = {
                t.public_number: t
                for t in Table.objects.filter(restaurant=restaurant, active=True)
            }

            tables_payload: list[dict[str, Any]] = []
            for td in cfg["tables"]:
                tbl = tables.get(td["public_number"])
                zn = zones.get(td["zone_name"])
                tables_payload.append({
                    "id": str(tbl.public_id) if tbl else None,
                    "public_number": td["public_number"],
                    "x": td["x"],
                    "y": td["y"],
                    "width": td["width"],
                    "height": td["height"],
                    "rotation": td["rotation"],
                    "shape": td["shape"],
                    "capacity": td["capacity"],
                    "zone_id": str(zn.public_id) if zn else None,
                    "tags": td.get("tags", []),
                })

            portals_payload: list[dict[str, Any]] = []
            for pd in cfg.get("portals", []):
                tz = zones.get(pd["target_zone_name"])
                portals_payload.append({
                    "x": pd["x"],
                    "y": pd["y"],
                    "width": pd["width"],
                    "height": pd["height"],
                    "target_zone_id": str(tz.public_id) if tz else None,
                    "label": pd.get("label", ""),
                })

            layout_json = {
                "tables": tables_payload,
                "obstacles": cfg.get("obstacles", []),
                "thresholds": cfg.get("thresholds", []),
                "portals": portals_payload,
            }

            parent = (
                LayoutVersion.objects.filter(restaurant=restaurant)
                .order_by("-published_at", "-id")
                .first()
            )

            LayoutVersion.objects.create(
                restaurant=restaurant,
                parent_version=parent,
                layout_json=layout_json,
                published_at=timezone.now(),
            )
            created_count += 1
            self.stdout.write(f"  Created layout for '{restaurant.name}'.")

        self.stdout.write(self.style.SUCCESS(f"Done: {created_count} layouts seeded."))
