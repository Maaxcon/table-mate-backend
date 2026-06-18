from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from apps.restaurants.models import Table, TableShape, Zone
from common.hall_events import emit_hall_layout_published

if TYPE_CHECKING:
    from apps.authentication.models import User

    from .models import LayoutVersion


def _generate_table_number(restaurant_id: int) -> str:
    existing = (
        Table.objects.filter(restaurant_id=restaurant_id)
        .values_list("table_number", flat=True)
    )
    max_num = 0
    for tn in existing:
        m = re.fullmatch(r"(\d+)", str(tn))
        if m:
            max_num = max(max_num, int(m.group(1)))
    return str(max_num + 1)


def update_table_position(
    table: Table,
    *,
    position_x: int | None,
    position_y: int | None,
) -> Table:
    if position_x is not None:
        table.position_x = position_x
    if position_y is not None:
        table.position_y = position_y
    table.save(update_fields=["position_x", "position_y", "updated_at"])
    return table


def _entities_by_id(entities: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {e["id"]: e for e in entities}


def compute_diff(
    old_entities: list[dict[str, Any]],
    new_entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    old_map = _entities_by_id(old_entities)
    new_map = _entities_by_id(new_entities)
    ops: list[dict[str, Any]] = []

    old_ids = set(old_map)
    new_ids = set(new_map)

    for eid in new_ids - old_ids:
        ops.append({"op": "add", "entity": new_map[eid]})

    for eid in old_ids - new_ids:
        ops.append({"op": "remove", "id": eid})

    for eid in old_ids & new_ids:
        old_e = old_map[eid]
        new_e = new_map[eid]
        patch: dict[str, Any] = {}
        for key in new_e:
            if key == "id":
                continue
            if new_e[key] != old_e.get(key):
                patch[key] = new_e[key]
        for key in old_e:
            if key == "id":
                continue
            if key not in new_e:
                patch[key] = None
        if patch:
            ops.append({"op": "update", "id": eid, "patch": patch})

    return ops


def apply_diff(
    entities: list[dict[str, Any]],
    diff: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result = list(entities)
    for op in diff:
        if op["op"] == "add":
            result.append(op["entity"])
        elif op["op"] == "remove":
            result = [e for e in result if e["id"] != op["id"]]
        elif op["op"] == "update":
            result = [
                {**e, **op["patch"]} if e["id"] == op["id"] else e
                for e in result
            ]
    return result


def rebuild_full_state(restaurant_id: int) -> list[dict[str, Any]]:
    from .models import LayoutVersion

    versions = list(
        LayoutVersion.objects.filter(restaurant_id=restaurant_id)
        .order_by("published_at", "id")
    )

    if not versions:
        return []

    entities: list[dict[str, Any]] = []
    for v in versions:
        data = v.layout_json
        if data.get("diff") is None:
            entities = list(data.get("entities", []))
        else:
            entities = apply_diff(entities, data["diff"])
    return entities


def _sync_tables_from_layout(
    *,
    restaurant_id: int,
    new_entities: list[dict[str, Any]],
    old_entities: list[dict[str, Any]],
) -> dict[str, Any]:
    from apps.reservations.models import Reservation

    warnings: list[dict[str, Any]] = []
    table_id_map: dict[str, str] = {}

    new_server_ids: set[str] = set()
    for entity in new_entities:
        sid = entity.get("server_id")
        if sid:
            new_server_ids.add(sid)

    for entity in new_entities:
        entity_type = entity.get("type")
        if not entity_type or not entity_type.startswith("table"):
            continue

        server_id = entity.get("server_id")
        shape = TableShape.ROUND if entity_type == "table-round" else TableShape.SQUARE
        position_x = int(entity.get("x", 0) * 100)
        position_y = int(entity.get("y", 0) * 100)
        capacity = entity.get("capacity", 4)
        table_number = entity.get("label", "")

        zone = None
        zone_id = entity.get("zoneId")
        if zone_id:
            try:
                zone = Zone.objects.get(public_id=zone_id, restaurant_id=restaurant_id)
            except Zone.DoesNotExist:
                pass

        if server_id:
            try:
                table = Table.objects.get(public_id=server_id, restaurant_id=restaurant_id)
                table.position_x = position_x
                table.position_y = position_y
                table.capacity = capacity
                table.shape = shape
                table.zone = zone
                if table_number:
                    table.table_number = table_number
                table.active = True
                table.save()
                table_id_map[entity["id"]] = str(table.public_id)
                continue
            except Table.DoesNotExist:
                pass

        if not table_number:
            table_number = _generate_table_number(restaurant_id)
        table = Table.objects.create(
            restaurant_id=restaurant_id,
            table_number=table_number,
            capacity=capacity,
            shape=shape,
            position_x=position_x,
            position_y=position_y,
            zone=zone,
        )
        table_id_map[entity["id"]] = str(table.public_id)

    for old_entity in old_entities:
        server_id = old_entity.get("server_id")
        if not server_id or server_id in new_server_ids:
            continue

        try:
            table = Table.objects.get(public_id=server_id, restaurant_id=restaurant_id)
        except Table.DoesNotExist:
            continue

        active_count = Reservation.objects.filter(
            table_id=table.pk,
            status__in=[Reservation.ReservationStatus.PENDING, Reservation.ReservationStatus.ACTIVE],
        ).count()

        if active_count > 0:
            warnings.append({
                "table_number": table.table_number,
                "reservation_count": active_count,
                "message": (
                    f"Table {table.table_number} has {active_count} active reservation(s). "
                    "It will be deactivated but kept in the database."
                ),
            })

        table.active = False
        table.save(update_fields=["active", "updated_at"])

    return {"table_id_map": table_id_map, "warnings": warnings}


def publish_layout(
    *,
    restaurant_id: int,
    layout_json: dict[str, object],
    published_by: User,
    parent_version: LayoutVersion | None = None,
) -> dict[str, Any]:
    from .models import LayoutVersion

    with transaction.atomic():
        if parent_version is None:
            parent_version = (
                LayoutVersion.objects.filter(restaurant_id=restaurant_id)
                .order_by("-published_at", "-id")
                .first()
            )

        new_entities = list(layout_json.get("tables", []))

        if parent_version is None:
            old_entities: list[dict[str, Any]] = []
            stored = {"diff": None, "entities": new_entities}
        else:
            old_entities = rebuild_full_state(restaurant_id)
            diff = compute_diff(old_entities, new_entities)
            stored = {"diff": diff}

        version = LayoutVersion.objects.create(
            restaurant_id=restaurant_id,
            parent_version=parent_version,
            layout_json=stored,
            published_at=timezone.now(),
            published_by=published_by,
        )

        sync_result = _sync_tables_from_layout(
            restaurant_id=restaurant_id,
            new_entities=new_entities,
            old_entities=old_entities,
        )

        transaction.on_commit(
            lambda: emit_hall_layout_published(
                restaurant_id=restaurant_id,
                layout_version_id=version.pk,
            )
        )
        return {
            "version": version,
            "table_id_map": sync_result["table_id_map"],
            "warnings": sync_result["warnings"],
        }
