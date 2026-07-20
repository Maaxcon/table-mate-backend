from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.editor.models import LayoutVersion
from apps.restaurants.models import Restaurant, Table, Zone

# All coordinates are in pixels, aligned to a 100px grid.
# Grid-unit positions: x/100, y/100. Dimensions: w/100, h/100 grid cells.


def _t(
    num: str,
    gx: int,
    gy: int,
    gw: int,
    gh: int,
    shape: str,
    cap: int,
    zone: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "public_number": num,
        "x": gx * 100,
        "y": gy * 100,
        "width": gw * 100,
        "height": gh * 100,
        "rotation": 0,
        "shape": shape,
        "capacity": cap,
        "zone_name": zone,
        "tags": tags or [],
    }


def _obs(gx: int, gy: int, gw: int, gh: int, zone: str = "", rotation: int = 0) -> dict[str, Any]:
    return {
        "x": gx * 100,
        "y": gy * 100,
        "width": gw * 100,
        "height": gh * 100,
        "rotation": rotation,
        "zone_name": zone,
    }


def _portal(gx: int, gy: int, gw: int, gh: int, target_zone: str, label: str, zone: str = "") -> dict[str, Any]:
    return {
        "x": gx * 100,
        "y": gy * 100,
        "width": gw * 100,
        "height": gh * 100,
        "target_zone_name": target_zone,
        "portal_label": label,
        "zone_name": zone,
    }


_LAYOUTS: dict[str, dict[str, Any]] = {
    "UniTable": {
        "tables": [
            # ── Main Hall ──
            _t("kathe", 21, 2, 4, 2, "square", 1, "Main Hall"),
            _t("marie", 25, 4, 2, 3, "square", 1, "Main Hall"),
            _t("mini", 21, 10, 2, 2, "square", 2, "Main Hall"),
            _t("T1", 9, 15, 7, 2, "square", 3, "Main Hall", ["quiet"]),
            _t("T1.5", 16, 15, 7, 2, "square", 3, "Main Hall"),
            _t("переговорка", 12, 3, 4, 6, "square", 8, "Main Hall"),
            # ── Open Space ──
            _t("T2", 1, 3, 7, 4, "square", 4, "Open Space"),
            _t("T3", 11, 3, 7, 4, "square", 4, "Open Space", ["window"]),
            _t("T4", 11, 16, 5, 8, "square", 6, "Open Space"),
            _t("T5", 21, 3, 8, 4, "square", 6, "Open Space", ["window"]),
            _t("T6", 23, 16, 5, 5, "square", 4, "Open Space"),
            _t("T6.5", 23, 21, 5, 5, "square", 4, "Open Space"),
            # ── Roof ──
            _t("T7", 21, 2, 4, 6, "square", 4, "Roof"),
            _t("T8", 21, 12, 4, 6, "square", 4, "Roof"),
        ],
        "obstacles": [
            # Main Hall
            _obs(8, 7, 1, 5, "Main Hall"),
            _obs(12, 0, 5, 1, "Main Hall"),
            _obs(19, 1, 1, 8, "Main Hall"),
            _obs(9, 11, 4, 1, "Main Hall"),
            _obs(19, 9, 1, 3, "Main Hall", rotation=45),
            _obs(15, 11, 3, 1, "Main Hall"),
            _obs(0, 7, 1, 2, "Main Hall"),
            _obs(16, 17, 8, 1, "Main Hall"),
            _obs(0, 12, 1, 5, "Main Hall"),
            _obs(8, 17, 8, 1, "Main Hall"),
            _obs(28, 0, 1, 6, "Main Hall"),
            _obs(17, 0, 4, 1, "Main Hall"),
            _obs(25, 0, 3, 1, "Main Hall"),
            _obs(28, 6, 1, 2, "Main Hall"),
            _obs(25, 8, 4, 1, "Main Hall"),
            _obs(24, 17, 5, 1, "Main Hall"),
            _obs(8, 0, 4, 1, "Main Hall"),
            _obs(20, 8, 3, 1, "Main Hall"),
            _obs(8, 1, 1, 3, "Main Hall"),
            _obs(8, 12, 1, 2, "Main Hall"),
            _obs(8, 16, 1, 1, "Main Hall"),
            # Open Space
            _obs(0, 5, 1, 4, "Open Space"),
            _obs(0, 1, 1, 4, "Open Space"),
            _obs(0, 0, 2, 1, "Open Space"),
            _obs(18, 1, 1, 6, "Open Space"),
            _obs(8, 0, 3, 1, "Open Space"),
            _obs(0, 14, 1, 5, "Open Space"),
            _obs(0, 22, 1, 5, "Open Space"),
            _obs(1, 26, 8, 1, "Open Space"),
            _obs(9, 26, 8, 1, "Open Space"),
            _obs(17, 0, 2, 1, "Open Space"),
            _obs(18, 21, 1, 6, "Open Space"),
            _obs(17, 26, 1, 1, "Open Space"),
            _obs(18, 16, 1, 5, "Open Space"),
            _obs(19, 0, 3, 1, "Open Space"),
            _obs(28, 0, 1, 1, "Open Space"),
            _obs(32, 5, 1, 1, "Open Space"),
            _obs(32, 11, 1, 1, "Open Space"),
            _obs(32, 18, 1, 1, "Open Space"),
            _obs(32, 25, 1, 2, "Open Space"),
            _obs(19, 26, 8, 1, "Open Space"),
            _obs(27, 26, 5, 1, "Open Space"),
        ],
        "thresholds": [
            # Main Hall
            {
                "x": 100,
                "y": 300,
                "width": 700,
                "height": 400,
                "label": "перекур",
                "rotation": 0,
                "zone_name": "Main Hall",
            },
            {
                "x": 800,
                "y": 400,
                "width": 100,
                "height": 300,
                "label": "window",
                "rotation": 0,
                "zone_name": "Main Hall",
            },
            {
                "x": 0,
                "y": 900,
                "width": 100,
                "height": 300,
                "label": "entrance",
                "rotation": 0,
                "zone_name": "Main Hall",
            },
            {
                "x": 0,
                "y": 1700,
                "width": 400,
                "height": 200,
                "label": "kitchen",
                "rotation": 0,
                "zone_name": "Main Hall",
            },
            {
                "x": 400,
                "y": 1700,
                "width": 400,
                "height": 200,
                "label": "restroom",
                "rotation": 0,
                "zone_name": "Main Hall",
            },
            {
                "x": 2100,
                "y": 0,
                "width": 400,
                "height": 100,
                "label": "window",
                "rotation": 0,
                "zone_name": "Main Hall",
            },
            {
                "x": 2300,
                "y": 1600,
                "width": 600,
                "height": 100,
                "label": "couch",
                "rotation": 0,
                "zone_name": "Main Hall",
            },
            # Open Space
            {
                "x": 200,
                "y": 0,
                "width": 600,
                "height": 100,
                "label": "window",
                "rotation": 0,
                "zone_name": "Open Space",
            },
            {
                "x": 1800,
                "y": 700,
                "width": 100,
                "height": 100,
                "label": "mini-bar",
                "rotation": 0,
                "zone_name": "Open Space",
            },
            {
                "x": 1100,
                "y": 0,
                "width": 600,
                "height": 100,
                "label": "window",
                "rotation": 0,
                "zone_name": "Open Space",
            },
            {
                "x": 800,
                "y": 100,
                "width": 300,
                "height": 100,
                "label": "air cond",
                "rotation": 0,
                "zone_name": "Open Space",
            },
            {
                "x": 100,
                "y": 2400,
                "width": 300,
                "height": 200,
                "label": "silent",
                "rotation": 0,
                "zone_name": "Open Space",
            },
            {
                "x": 400,
                "y": 2400,
                "width": 500,
                "height": 200,
                "label": "boxes",
                "rotation": 0,
                "zone_name": "Open Space",
            },
            {
                "x": 2200,
                "y": 0,
                "width": 600,
                "height": 100,
                "label": "window",
                "rotation": 0,
                "zone_name": "Open Space",
            },
            {
                "x": 2900,
                "y": 200,
                "width": 500,
                "height": 100,
                "label": "window",
                "rotation": 45,
                "zone_name": "Open Space",
            },
            {
                "x": 3200,
                "y": 1900,
                "width": 100,
                "height": 600,
                "label": "window",
                "rotation": 0,
                "zone_name": "Open Space",
            },
            {
                "x": 3200,
                "y": 1200,
                "width": 100,
                "height": 600,
                "label": "window",
                "rotation": 0,
                "zone_name": "Open Space",
            },
            {
                "x": 3200,
                "y": 600,
                "width": 100,
                "height": 500,
                "label": "window",
                "rotation": 0,
                "zone_name": "Open Space",
            },
            # Roof
            {"x": 500, "y": 800, "width": 700, "height": 300, "label": "tennis", "rotation": 0, "zone_name": "Roof"},
        ],
        "portals": [
            {
                "x": 2900,
                "y": 900,
                "width": 200,
                "height": 700,
                "portal_label": "open space",
                "target_zone_name": "Open Space",
                "zone_name": "Main Hall",
            },
            {
                "x": -100,
                "y": 900,
                "width": 200,
                "height": 500,
                "portal_label": "Main Hall",
                "target_zone_name": "Main Hall",
                "zone_name": "Open Space",
            },
            {
                "x": -100,
                "y": 1900,
                "width": 200,
                "height": 300,
                "portal_label": "Roof",
                "target_zone_name": "Roof",
                "zone_name": "Open Space",
            },
            {
                "x": -100,
                "y": 1700,
                "width": 200,
                "height": 300,
                "portal_label": "Open Space",
                "target_zone_name": "Open Space",
                "zone_name": "Roof",
            },
        ],
    },
    "Table Mate Terrace": {
        "tables": [
            _t("T1", 1, 1, 3, 3, "round", 2, "Indoor"),
            _t("T2", 1, 5, 3, 3, "round", 2, "Indoor"),
            _t("T3", 5, 1, 3, 3, "square", 4, "Indoor"),
            _t("T4", 9, 1, 3, 3, "square", 4, "Terrace", ["window"]),
            _t("T5", 9, 5, 3, 3, "square", 6, "Terrace"),
        ],
        "obstacles": [
            _obs(0, 0, 8, 1, "Indoor"),
        ],
        "thresholds": [],
        "portals": [
            _portal(7, 3, 2, 2, "Terrace", "Terrace", "Indoor"),
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
                self.stdout.write(self.style.WARNING(f"No layout config for '{restaurant.name}', skipping."))
                continue

            zones = {z.name: z for z in Zone.objects.filter(restaurant=restaurant)}
            tables = {t.public_number: t for t in Table.objects.filter(restaurant=restaurant, active=True)}

            def _zone_id(name: str, *, _zones: dict[str, Zone] = zones) -> str:
                z = _zones.get(name) or next(iter(_zones.values()), None)
                return str(z.public_id) if z else ""

            tables_payload: list[dict[str, Any]] = []
            for td in cfg["tables"]:
                tbl = tables.get(td["public_number"])
                tables_payload.append(
                    {
                        "id": str(tbl.public_id) if tbl else None,
                        "public_number": td["public_number"],
                        "x": td["x"],
                        "y": td["y"],
                        "width": td["width"],
                        "height": td["height"],
                        "rotation": td["rotation"],
                        "shape": td["shape"],
                        "capacity": td["capacity"],
                        "zone_id": _zone_id(td["zone_name"]),
                        "tags": td.get("tags", []),
                    }
                )

            portals_payload: list[dict[str, Any]] = []
            for pd in cfg.get("portals", []):
                tz = zones.get(pd["target_zone_name"])
                portals_payload.append(
                    {
                        "x": pd["x"],
                        "y": pd["y"],
                        "width": pd["width"],
                        "height": pd["height"],
                        "target_zone_id": str(tz.public_id) if tz else None,
                        "portal_label": pd.get("portal_label") or pd.get("label", ""),
                        "zone_id": _zone_id(pd.get("zone_name", "")),
                    }
                )

            obstacles_payload: list[dict[str, Any]] = []
            for od in cfg.get("obstacles", []):
                obstacles_payload.append(
                    {
                        "x": od["x"],
                        "y": od["y"],
                        "width": od["width"],
                        "height": od["height"],
                        "rotation": od.get("rotation", 0),
                        "zone_id": _zone_id(od.get("zone_name", "")),
                    }
                )

            thresholds_payload: list[dict[str, Any]] = []
            for thd in cfg.get("thresholds", []):
                thresholds_payload.append(
                    {
                        "x": thd["x"],
                        "y": thd["y"],
                        "width": thd["width"],
                        "height": thd["height"],
                        "rotation": thd.get("rotation", 0),
                        "label": thd.get("label", ""),
                        "zone_id": _zone_id(thd.get("zone_name", "")),
                    }
                )

            layout_json = {
                "tables": tables_payload,
                "obstacles": obstacles_payload,
                "thresholds": thresholds_payload,
                "portals": portals_payload,
            }

            parent = LayoutVersion.objects.filter(restaurant=restaurant).order_by("-published_at", "-id").first()

            LayoutVersion.objects.create(
                restaurant=restaurant,
                parent_version=parent,
                layout_json=layout_json,
                published_at=timezone.now(),
            )

            created_count += 1
            self.stdout.write(f"  Created layout for '{restaurant.name}'.")

        self.stdout.write(self.style.SUCCESS(f"Done: {created_count} layouts seeded."))
