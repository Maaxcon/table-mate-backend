from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.restaurants.models import Table, Zone
from common.hall_events import emit_hall_layout_published

if TYPE_CHECKING:
    from apps.authentication.models import User



class TableInUseError(Exception):
    """Raised when attempting to soft-delete a table with active reservations/sessions."""


def _to_jsonable(value: Any) -> Any:
    """Recursively convert UUIDs to strings so the layout can be stored in a JSONField.

    DRF's ``UUIDField`` deserializes ``id``/``zone_id``/``target_zone_id`` into
    ``uuid.UUID`` objects, which the default JSON encoder cannot serialize.
    """
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    return value


def _generate_public_number(restaurant_id: int) -> str:
    active_nums: set[int] = set()
    inactive_nums: set[int] = set()

    for pn, active in (
        Table.objects.filter(restaurant_id=restaurant_id)
        .values_list("public_number", "active")
    ):
        m = re.fullmatch(r"T(\d+)", str(pn))
        if m:
            num = int(m.group(1))
            if active:
                active_nums.add(num)
            else:
                inactive_nums.add(num)

    reusable = sorted(inactive_nums - active_nums)
    if reusable:
        return f"T{reusable[0]}"

    max_num = max(active_nums | inactive_nums, default=0)
    return f"T{max_num + 1}"


@transaction.atomic
def publish_layout(
    *,
    restaurant_id: int,
    restaurant_public_id: str,
    layout_data: dict[str, Any],
    published_by: User,
) -> dict[str, Any]:
    from apps.orders.models import Session, SessionStatus
    from apps.reservations.models import Reservation, ReservationStatus

    from .models import LayoutVersion

    # ``deleted_table_ids`` is a publish-time instruction, not part of the persisted
    # layout geometry — pull it out so it never lands in the stored payload.
    deleted_table_ids = layout_data.pop("deleted_table_ids", [])

    existing_tables = {
        str(t.public_id): t
        for t in Table.objects.filter(restaurant_id=restaurant_id, active=True)
    }
    incoming_table_uuids: set[str] = set()
    table_id_map: dict[str, str] = {}
    public_number_map: dict[str, str] = {}

    for table_data in layout_data.get("tables", []):
        table_uuid = table_data.get("id")
        client_uuid = table_data.get("_client_id")
        public_number = table_data.get("public_number") or ""
        capacity = table_data["capacity"]
        zone_id = table_data.get("zone_id")
        zone = (
            Zone.objects.filter(public_id=zone_id, restaurant_id=restaurant_id).first()
            if zone_id
            else None
        )
        # Table.zone is non-nullable; a missing/stale zone_id is bad input, not a 500.
        if zone is None:
            raise ValidationError(f"Table references unknown zone_id {zone_id!r}.")

        existing = None
        client_id = None

        # 1. Match by UUID if provided and found in DB
        if table_uuid and str(table_uuid) in existing_tables:
            existing = existing_tables[str(table_uuid)]
            client_id = str(table_uuid)
        # 2. Fallback: match by public_number (handles missing/stale UUID)
        elif public_number:
            match = Table.objects.filter(
                restaurant_id=restaurant_id, public_number=public_number, active=True
            ).first()
            if match:
                existing = match
                client_id = str(table_uuid) if table_uuid else str(match.public_id)

        if existing:
            existing.capacity = capacity
            existing.zone = zone
            existing.active = True
            if public_number:
                existing.public_number = public_number
            existing.save()
            incoming_table_uuids.add(str(existing.public_id))
            if client_id:
                table_id_map[client_id] = str(existing.public_id)
            table_data["id"] = str(existing.public_id)
            table_data["public_number"] = existing.public_number
            pn_key = str(client_uuid) if client_uuid else (str(table_uuid) if table_uuid else None)
            if pn_key:
                public_number_map[pn_key] = existing.public_number
        else:
            if not public_number:
                public_number = _generate_public_number(restaurant_id)
            table = Table.objects.create(
                restaurant_id=restaurant_id,
                public_number=public_number,
                capacity=capacity,
                zone=zone,
            )
            client_id = str(table_uuid) if table_uuid else str(table.public_id)
            incoming_table_uuids.add(str(table.public_id))
            table_id_map[client_id] = str(table.public_id)
            table_data["id"] = str(table.public_id)
            table_data["public_number"] = table.public_number
            pn_key = str(client_uuid) if client_uuid else (str(table_uuid) if table_uuid else None)
            if pn_key:
                public_number_map[pn_key] = table.public_number

    # Deletions are explicit: only tables the admin actually removed (sent in
    # ``deleted_table_ids``) are deactivated. Moving/resizing/editing a table is an
    # upsert on the same row above, so its reservations/sessions stay linked and it is
    # never treated as removed. A table absent from both the incoming layout and the
    # delete list is left untouched (still active).
    for raw_id in deleted_table_ids:
        deleted_table = existing_tables.get(str(raw_id))
        if deleted_table is None or str(deleted_table.public_id) in incoming_table_uuids:
            # Unknown, already-inactive, or re-added in the same publish: nothing to do.
            continue

        has_active_reservation = Reservation.objects.filter(
            table_id=deleted_table.pk,
            status__in=[ReservationStatus.PENDING, ReservationStatus.ACTIVE],
        ).exists()

        has_open_session = Session.objects.filter(
            table_id=deleted_table.pk,
            status=SessionStatus.OPEN,
        ).exists()

        if has_active_reservation or has_open_session:
            raise TableInUseError(
                f"Table {deleted_table.public_number} has active reservations or sessions. "
                "Reassign them before removing."
            )

        deleted_table.active = False
        deleted_table.save(update_fields=["active", "updated_at"])

    # Normalize UUID objects (zone_id, target_zone_id, ...) to strings before the
    # layout is written to the JSONField.
    layout_json = _to_jsonable(layout_data)

    parent_version = (
        LayoutVersion.objects.filter(restaurant_id=restaurant_id)
        .order_by("-published_at", "-id")
        .first()
    )

    version = LayoutVersion.objects.create(
        restaurant_id=restaurant_id,
        parent_version=parent_version,
        layout_json=layout_json,
        published_at=timezone.now(),
        published_by=published_by,
    )

    transaction.on_commit(
        lambda: emit_hall_layout_published(
            restaurant_id=restaurant_id,
            layout_version_id=version.pk,
            layout_version_public_id=str(version.public_id),
            restaurant_public_id=restaurant_public_id,
        )
    )

    return {
        "version": version,
        "table_id_map": table_id_map,
        "public_number_map": public_number_map,
    }
