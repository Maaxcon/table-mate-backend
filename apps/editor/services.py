from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from apps.restaurants.models import Table, TableShape, Zone
from common.hall_events import emit_hall_layout_published

if TYPE_CHECKING:
    from apps.authentication.models import User



class TableInUseError(Exception):
    """Raised when attempting to soft-delete a table with active reservations/sessions."""


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


def _resolve_shape(shape_str: str) -> str:
    mapping = {
        "round": TableShape.ROUND,
        "square": TableShape.SQUARE,
        "rectangle": TableShape.RECTANGLE,
        "booth": TableShape.BOOTH,
    }
    return mapping.get(shape_str, TableShape.RECTANGLE)


@transaction.atomic
def publish_layout(
    *,
    restaurant_id: int,
    layout_data: dict[str, Any],
    published_by: User,
) -> dict[str, Any]:
    from apps.orders.models import Session, SessionStatus
    from apps.reservations.models import Reservation, ReservationStatus

    from .models import Layout, LayoutVersion

    existing_tables = {
        str(t.public_id): t
        for t in Table.objects.filter(restaurant_id=restaurant_id, active=True)
    }
    incoming_table_uuids: set[str] = set()
    table_id_map: dict[str, str] = {}
    warnings: list[dict[str, Any]] = []

    for table_data in layout_data.get("tables", []):
        table_uuid = table_data.get("id")
        zone = None
        zone_id = table_data.get("zone_id")
        if zone_id:
            zone = Zone.objects.filter(public_id=zone_id, restaurant_id=restaurant_id).first()

        shape = _resolve_shape(table_data["shape"])
        capacity = table_data["capacity"]
        public_number = table_data.get("public_number") or ""

        if table_uuid and str(table_uuid) in existing_tables:
            table = existing_tables[str(table_uuid)]
            table.capacity = capacity
            table.shape = shape
            table.zone = zone
            table.active = True
            if public_number:
                table.public_number = public_number
            table.save()
            incoming_table_uuids.add(str(table_uuid))
            table_id_map[str(table_uuid)] = str(table.public_id)
        else:
            if not public_number:
                public_number = _generate_public_number(restaurant_id)

            table = Table.objects.create(
                restaurant_id=restaurant_id,
                public_number=public_number,
                capacity=capacity,
                shape=shape,
                zone=zone,
            )
            client_id = str(table_uuid) if table_uuid else str(table.public_id)
            incoming_table_uuids.add(str(table.public_id))
            table_id_map[client_id] = str(table.public_id)

    for public_id, table in existing_tables.items():
        if public_id in incoming_table_uuids:
            continue

        has_active_reservation = Reservation.objects.filter(
            table_id=table.pk,
            status__in=[ReservationStatus.PENDING, ReservationStatus.ACTIVE],
        ).exists()

        has_open_session = Session.objects.filter(
            table_id=table.pk,
            status=SessionStatus.OPEN,
        ).exists()

        if has_active_reservation or has_open_session:
            raise TableInUseError(
                f"Table {table.public_number} has active reservations or sessions. "
                "Reassign them before removing."
            )

        table.active = False
        table.save(update_fields=["active", "updated_at"])

    parent_version = (
        LayoutVersion.objects.filter(restaurant_id=restaurant_id)
        .order_by("-published_at", "-id")
        .first()
    )

    version = LayoutVersion.objects.create(
        restaurant_id=restaurant_id,
        parent_version=parent_version,
        layout_json=layout_data,
        published_at=timezone.now(),
        published_by=published_by,
    )

    last_layout = (
        Layout.objects.filter(restaurant_id=restaurant_id)
        .order_by("-version")
        .first()
    )
    next_version = (last_layout.version + 1) if last_layout else 1
    Layout.objects.create(
        restaurant_id=restaurant_id,
        version=next_version,
        payload=layout_data,
        published_at=timezone.now(),
        published_by=published_by,
    )

    transaction.on_commit(
        lambda: emit_hall_layout_published(
            restaurant_id=restaurant_id,
            layout_version_id=version.pk,
        )
    )

    return {
        "version": version,
        "table_id_map": table_id_map,
        "warnings": warnings,
    }
