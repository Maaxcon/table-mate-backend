from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.editor.models import Layout, LayoutVersion
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


def _obs(gx: int, gy: int, gw: int, gh: int, zone: str = "") -> dict[str, Any]:
    return {
        "x": gx * 100,
        "y": gy * 100,
        "width": gw * 100,
        "height": gh * 100,
        "rotation": 0,
        "zone_name": zone,
    }


def _portal(
    gx: int, gy: int, gw: int, gh: int, target_zone: str, label: str, zone: str = ""
) -> dict[str, Any]:
    return {
        "x": gx * 100,
        "y": gy * 100,
        "width": gw * 100,
        "height": gh * 100,
        "target_zone_name": target_zone,
        "label": label,
        "zone_name": zone,
    }


_LAYOUTS: dict[str, dict[str, Any]] = {
    "Table Mate": {
        "tables": [
            # Main Hall (T1-T5)
            _t("T1", 1, 1, 3, 3, "round", 2, "Main Hall", ["window"]),
            _t("T2", 1, 5, 3, 3, "round", 2, "Main Hall"),
            _t("T3", 5, 1, 3, 3, "square", 4, "Main Hall"),
            _t("T4", 5, 5, 3, 3, "square", 4, "Main Hall", ["quiet"]),
            _t("T5", 5, 9, 3, 3, "square", 4, "Main Hall"),
            # VIP Room (T6-T7)
            _t("T6", 11, 1, 3, 3, "square", 6, "VIP Room"),
            _t("T7", 11, 5, 3, 3, "square", 6, "VIP Room"),
            # Winter Garden (T8-T10)
            _t("T8", 17, 1, 4, 3, "rectangle", 8, "Winter Garden", ["window"]),
            _t("T9", 17, 5, 3, 3, "square", 4, "Winter Garden"),
            _t("T10", 17, 9, 3, 3, "square", 4, "Winter Garden"),
        ],
        "obstacles": [
            _obs(0, 0, 22, 1, "Main Hall"),
            _obs(0, 14, 22, 1, "Main Hall"),
        ],
        "thresholds": [
            {"x": 1400, "y": 900, "width": 300, "height": 100, "zone_name": "Main Hall"},
        ],
        "portals": [
            _portal(14, 9, 2, 2, "VIP Room", "VIP Room", "Main Hall"),
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
            _obs(0, 0, 14, 1, "Indoor"),
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
                pz = zones.get(pd.get("zone_name", ""))
                portals_payload.append({
                    "x": pd["x"],
                    "y": pd["y"],
                    "width": pd["width"],
                    "height": pd["height"],
                    "target_zone_id": str(tz.public_id) if tz else None,
                    "label": pd.get("label", ""),
                    "zone_id": str(pz.public_id) if pz else None,
                })

            obstacles_payload: list[dict[str, Any]] = []
            for od in cfg.get("obstacles", []):
                oz = zones.get(od.get("zone_name", ""))
                obstacles_payload.append({
                    "x": od["x"],
                    "y": od["y"],
                    "width": od["width"],
                    "height": od["height"],
                    "rotation": od.get("rotation", 0),
                    "zone_id": str(oz.public_id) if oz else None,
                })

            thresholds_payload: list[dict[str, Any]] = []
            for thd in cfg.get("thresholds", []):
                thz = zones.get(thd.get("zone_name", ""))
                thresholds_payload.append({
                    "x": thd["x"],
                    "y": thd["y"],
                    "width": thd["width"],
                    "height": thd["height"],
                    "zone_id": str(thz.public_id) if thz else None,
                })

            layout_json = {
                "tables": tables_payload,
                "obstacles": obstacles_payload,
                "thresholds": thresholds_payload,
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

            last_layout = (
                Layout.objects.filter(restaurant=restaurant)
                .order_by("-version")
                .first()
            )
            next_version = (last_layout.version + 1) if last_layout else 1
            Layout.objects.create(
                restaurant=restaurant,
                version=next_version,
                payload=layout_json,
                published_at=timezone.now(),
            )

            created_count += 1
            self.stdout.write(f"  Created layout for '{restaurant.name}'.")

        self.stdout.write(self.style.SUCCESS(f"Done: {created_count} layouts seeded."))
