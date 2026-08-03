import uuid
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


def _entity_id(kind: str, zone: str, label: str, x: int, y: int, w: int, h: int) -> str:
    key = f"{kind}:{zone}:{label}:{x}:{y}:{w}:{h}"
    return str(uuid.uuid5(uuid.NAMESPACE_OID, key))


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
    "Смак Дому": {
        "tables": [
            # ── Зал ──
            _t("1", 1, 1, 3, 2, "round", 2, "Зал"),
            _t("2", 5, 1, 3, 2, "round", 2, "Зал"),
            _t("3", 1, 4, 4, 3, "square", 4, "Зал", ["window"]),
            _t("4", 6, 4, 4, 3, "square", 4, "Зал"),
            _t("5", 1, 8, 5, 3, "square", 6, "Зал"),
            _t("6", 7, 8, 6, 3, "square", 8, "Зал"),
            _t("7", 1, 12, 8, 4, "square", 10, "Зал"),
            # ── Літня тераса ──
            _t("В1", 1, 1, 3, 2, "round", 2, "Літня тераса"),
            _t("В2", 5, 1, 3, 2, "round", 2, "Літня тераса"),
            _t("В3", 1, 4, 4, 3, "square", 4, "Літня тераса", ["window"]),
            _t("В4", 6, 4, 4, 3, "square", 4, "Літня тераса"),
        ],
        "obstacles": [
            _obs(11, 0, 3, 1, "Зал"),
            _obs(0, 17, 1, 1, "Зал"),
            _obs(15, 17, 1, 1, "Зал"),
            _obs(0, 7, 1, 1, "Зал"),
            _obs(14, 4, 1, 3, "Зал"),
            _obs(12, 1, 4, 1, "Літня тераса"),
        ],
        "thresholds": [
            {
                "x": 0, "y": 600, "width": 100, "height": 400,
                "label": "вхід", "rotation": 0, "zone_name": "Зал",
            },
            {
                "x": 1500, "y": 0, "width": 400, "height": 100,
                "label": "кухня", "rotation": 0, "zone_name": "Зал",
            },
        ],
        "portals": [
            _portal(15, 10, 2, 2, "Літня тераса", "Тераса", "Зал"),
            _portal(-1, 6, 2, 2, "Зал", "Зал", "Літня тераса"),
        ],
    },
    "Барва": {
        "tables": [
            # ── Основний зал ──
            _t("A1", 1, 1, 3, 2, "round", 2, "Основний зал"),
            _t("A2", 5, 1, 3, 2, "round", 2, "Основний зал"),
            _t("A3", 1, 4, 4, 3, "square", 4, "Основний зал", ["window"]),
            _t("A4", 6, 4, 4, 3, "square", 4, "Основний зал"),
            _t("A5", 1, 8, 5, 4, "square", 6, "Основний зал"),
            _t("A6", 7, 8, 5, 4, "square", 6, "Основний зал"),
            _t("A7", 1, 13, 7, 4, "square", 8, "Основний зал"),
            # ── Барна зона ──
            _t("Б1", 1, 1, 2, 2, "round", 2, "Барна зона", ["window"]),
            _t("Б2", 4, 1, 2, 2, "round", 2, "Барна зона"),
            _t("Б3", 7, 1, 2, 2, "round", 2, "Барна зона"),
            _t("Б4", 1, 4, 4, 3, "square", 4, "Барна зона"),
            # ── VIP-кімната ──
            _t("V1", 1, 1, 6, 5, "square", 12, "VIP-кімната"),
        ],
        "obstacles": [
            _obs(10, 0, 2, 1, "Основний зал"),
            _obs(0, 18, 1, 2, "Основний зал"),
            _obs(13, 0, 3, 1, "Барна зона"),
            _obs(0, 7, 1, 3, "Барна зона"),
            _obs(6, 0, 2, 1, "VIP-кімната"),
            _obs(0, 6, 1, 2, "VIP-кімната"),
        ],
        "thresholds": [
            {
                "x": 0, "y": 600, "width": 100, "height": 400,
                "label": "вхід", "rotation": 0, "zone_name": "Основний зал",
            },
            {
                "x": 1300, "y": 600, "width": 100, "height": 400,
                "label": "кухня", "rotation": 0, "zone_name": "Основний зал",
            },
        ],
        "portals": [
            _portal(16, 2, 2, 4, "Барна зона", "Бар", "Основний зал"),
            _portal(-1, 4, 2, 3, "Основний зал", "Основний зал", "Барна зона"),
            _portal(10, 2, 2, 3, "VIP-кімната", "VIP", "Барна зона"),
            _portal(-1, 2, 2, 3, "Барна зона", "Бар", "VIP-кімната"),
        ],
    },
    "Козацький Двір": {
        "tables": [
            # ── Великий зал ──
            _t("К1", 1, 1, 4, 3, "square", 4, "Великий зал"),
            _t("К2", 6, 1, 4, 3, "square", 4, "Великий зал"),
            _t("К3", 1, 5, 5, 4, "square", 6, "Великий зал", ["window"]),
            _t("К4", 7, 5, 5, 4, "square", 6, "Великий зал"),
            _t("К5", 1, 10, 6, 4, "square", 8, "Великий зал"),
            _t("К6", 8, 10, 6, 4, "square", 10, "Великий зал"),
            _t("К7", 1, 15, 8, 5, "square", 12, "Великий зал"),
            # ── Козацька хата ──
            _t("Х1", 1, 1, 3, 2, "round", 2, "Козацька хата"),
            _t("Х2", 1, 4, 4, 3, "square", 4, "Козацька хата"),
            _t("Х3", 6, 1, 5, 4, "square", 6, "Козацька хата", ["window"]),
            # ── Двір ──
            _t("Д1", 1, 1, 4, 3, "square", 4, "Двір"),
            _t("Д2", 6, 1, 4, 3, "square", 4, "Двір"),
            _t("Д3", 1, 5, 5, 4, "square", 6, "Двір", ["window"]),
            _t("Д4", 7, 5, 5, 4, "square", 8, "Двір"),
            _t("Д5", 1, 10, 7, 5, "square", 10, "Двір"),
        ],
        "obstacles": [
            _obs(14, 0, 2, 1, "Великий зал"),
            _obs(0, 21, 1, 1, "Великий зал"),
            _obs(10, 0, 2, 1, "Козацька хата"),
            _obs(0, 8, 1, 2, "Козацька хата"),
            _obs(12, 0, 2, 1, "Двір"),
            _obs(0, 15, 1, 1, "Двір"),
        ],
        "thresholds": [
            {
                "x": 0, "y": 800, "width": 100, "height": 400,
                "label": "вхід", "rotation": 0, "zone_name": "Великий зал",
            },
            {
                "x": 1400, "y": 0, "width": 200, "height": 100,
                "label": "кухня", "rotation": 0, "zone_name": "Великий зал",
            },
        ],
        "portals": [
            _portal(15, 3, 2, 4, "Козацька хата", "Хата", "Великий зал"),
            _portal(-1, 3, 2, 3, "Великий зал", "Зал", "Козацька хата"),
            _portal(10, 10, 2, 3, "Двір", "Двір", "Великий зал"),
            _portal(-1, 5, 2, 3, "Великий зал", "Зал", "Двір"),
        ],
    },
    "Море Смаку": {
        "tables": [
            # ── Головний зал ──
            _t("M1", 1, 1, 3, 2, "round", 2, "Головний зал"),
            _t("M2", 5, 1, 3, 2, "round", 2, "Головний зал"),
            _t("M3", 1, 4, 4, 3, "square", 4, "Головний зал", ["window"]),
            _t("M4", 6, 4, 4, 3, "square", 4, "Головний зал"),
            _t("M5", 1, 8, 5, 4, "square", 6, "Головний зал"),
            _t("M6", 7, 8, 6, 4, "square", 8, "Головний зал"),
            # ── Тераса біля води ──
            _t("T1", 1, 1, 3, 2, "round", 2, "Тераса біля води"),
            _t("T2", 5, 1, 3, 2, "round", 2, "Тераса біля води"),
            _t("T3", 1, 4, 4, 3, "square", 4, "Тераса біля води", ["window"]),
            _t("T4", 6, 4, 4, 3, "square", 4, "Тераса біля води"),
            _t("T5", 1, 8, 5, 4, "square", 6, "Тераса біля води"),
        ],
        "obstacles": [
            _obs(11, 0, 2, 1, "Головний зал"),
            _obs(0, 12, 1, 1, "Головний зал"),
            _obs(12, 0, 2, 1, "Тераса біля води"),
            _obs(0, 12, 1, 1, "Тераса біля води"),
        ],
        "thresholds": [
            {
                "x": 0, "y": 600, "width": 100, "height": 400,
                "label": "вхід", "rotation": 0, "zone_name": "Головний зал",
            },
            {
                "x": 1100, "y": 0, "width": 200, "height": 100,
                "label": "кухня", "rotation": 0, "zone_name": "Головний зал",
            },
        ],
        "portals": [
            _portal(13, 3, 2, 3, "Тераса біля води", "Тераса", "Головний зал"),
            _portal(-1, 4, 2, 3, "Головний зал", "Зал", "Тераса біля води"),
        ],
    },
    "Вогнище": {
        "tables": [
            # ── Зал біля каміну ──
            _t("В1", 1, 1, 3, 2, "round", 2, "Зал біля каміну"),
            _t("В2", 5, 1, 3, 2, "round", 2, "Зал біля каміну"),
            _t("В3", 1, 4, 4, 3, "square", 4, "Зал біля каміну", ["window"]),
            # ── Основний зал ──
            _t("О1", 1, 1, 3, 2, "round", 2, "Основний зал"),
            _t("О2", 1, 4, 4, 3, "square", 4, "Основний зал", ["window"]),
            _t("О3", 6, 4, 4, 3, "square", 4, "Основний зал"),
            _t("О4", 1, 8, 5, 4, "square", 6, "Основний зал"),
            _t("О5", 7, 8, 5, 4, "square", 6, "Основний зал"),
            _t("О6", 1, 13, 6, 4, "square", 8, "Основний зал"),
            _t("О7", 8, 13, 6, 4, "square", 10, "Основний зал"),
            # ── Відкрита кухня ──
            _t("К1", 1, 1, 4, 3, "square", 4, "Відкрита кухня"),
            _t("К2", 6, 1, 5, 4, "square", 6, "Відкрита кухня"),
        ],
        "obstacles": [
            _obs(9, 0, 2, 1, "Зал біля каміну"),
            _obs(0, 7, 1, 1, "Зал біля каміну"),
            _obs(13, 0, 2, 1, "Основний зал"),
            _obs(0, 18, 1, 1, "Основний зал"),
            _obs(11, 0, 3, 1, "Відкрита кухня"),
            _obs(0, 6, 1, 1, "Відкрита кухня"),
        ],
        "thresholds": [
            {
                "x": 0, "y": 600, "width": 100, "height": 400,
                "label": "вхід", "rotation": 0, "zone_name": "Основний зал",
            },
            {
                "x": 1400, "y": 500, "width": 100, "height": 300,
                "label": "кухня", "rotation": 0, "zone_name": "Основний зал",
            },
        ],
        "portals": [
            _portal(5, 3, 2, 2, "Зал біля каміну", "Камін", "Основний зал"),
            _portal(-1, 4, 2, 2, "Основний зал", "Основний зал", "Зал біля каміну"),
            _portal(14, 3, 2, 3, "Відкрита кухня", "Кухня", "Основний зал"),
            _portal(-1, 3, 2, 3, "Основний зал", "Основний зал", "Відкрита кухня"),
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
                portal_label = pd.get("portal_label") or pd.get("label", "")
                portals_payload.append(
                    {
                        "id": _entity_id(
                            "portal",
                            pd.get("zone_name", ""),
                            portal_label,
                            pd["x"],
                            pd["y"],
                            pd["width"],
                            pd["height"],
                        ),
                        "x": pd["x"],
                        "y": pd["y"],
                        "width": pd["width"],
                        "height": pd["height"],
                        "target_zone_id": str(tz.public_id) if tz else None,
                        "label": portal_label,
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
                        "id": _entity_id(
                            "threshold",
                            thd.get("zone_name", ""),
                            thd.get("label", ""),
                            thd["x"],
                            thd["y"],
                            thd["width"],
                            thd["height"],
                        ),
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
