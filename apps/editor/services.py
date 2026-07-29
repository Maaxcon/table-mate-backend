from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.restaurants.models import Restaurant, Table, Zone
from common.hall_events import emit_hall_layout_published

if TYPE_CHECKING:
    from apps.authentication.models import User

    from .models import LayoutDraft

from .models import LayoutEntityTranslation


class TableInUseError(Exception):
    """Raised when attempting to soft-delete a table with active reservations/sessions."""


class LayoutVersionConflictError(Exception):
    """Raised when a publish is based on an outdated layout version."""

    def __init__(self, current_version_id: str | None) -> None:
        self.current_version_id = current_version_id
        super().__init__(
            "The floor plan was published by another admin. Reload the latest plan and reconcile your changes "
            "before publishing."
        )


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
    # Monotonic numbering: always one above the highest ``T<n>`` ever used,
    # active or inactive. Reusing a dead table's number made a freshly created
    # table silently reappear as a previously deleted one (the "ghost" T1 in two
    # zones), so we never recycle numbers.
    highest = 0
    for (pn,) in Table.objects.filter(restaurant_id=restaurant_id).values_list("public_number"):
        m = re.fullmatch(r"T(\d+)", str(pn))
        if m:
            highest = max(highest, int(m.group(1)))

    return f"T{highest + 1}"


@transaction.atomic
def publish_layout(
    *,
    restaurant_id: int,
    restaurant_public_id: str,
    layout_data: dict[str, Any],
    published_by: User,
    base_layout_version_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    from apps.orders.models import Session, SessionStatus
    from apps.reservations.models import Reservation, ReservationStatus

    from .models import LayoutVersion

    # Serialize concurrent publishes for the same restaurant: lock the restaurant
    # row so the second request waits for the first to complete, guaranteeing it
    # sees the fresh state (parent version, tables, zones, etc.).
    Restaurant.objects.select_for_update().get(pk=restaurant_id)

    parent_version = LayoutVersion.objects.filter(restaurant_id=restaurant_id).order_by("-published_at", "-id").first()
    if (parent_version is None and base_layout_version_id is not None) or (
        parent_version is not None and parent_version.public_id != base_layout_version_id
    ):
        raise LayoutVersionConflictError(str(parent_version.public_id) if parent_version else None)

    # ``deleted_table_ids`` and ``zones`` are publish-time instructions, not part of
    # the persisted layout geometry — pull them out so they never land in the stored payload.
    deleted_table_ids = layout_data.pop("deleted_table_ids", [])
    zones_data = layout_data.pop("zones", {})

    # ------------------------------------------------------------------
    # 0. Sweep orphan soft-deleted tables so editor churn (create -> delete
    #    without ever booking) does not pile up inactive rows. Only tables with
    #    no history are removed: ``sessions`` is PROTECT and ``reservations`` is
    #    SET_NULL, so anything ever used is kept and its records stay intact.
    # ------------------------------------------------------------------
    Table.objects.filter(
        restaurant_id=restaurant_id,
        active=False,
        sessions__isnull=True,
        reservations__isnull=True,
    ).delete()

    # ------------------------------------------------------------------
    # 1. Process zone creations (before entity processing so zones exist
    #    for table/obstacle/portal references).
    # ------------------------------------------------------------------
    zone_id_map: dict[str, str] = {}
    for create_data in zones_data.get("created", []):
        zone_client_id = str(create_data["_client_id"])
        created_zone = Zone.objects.create(
            restaurant_id=restaurant_id,
            name=create_data["name"],
            canvas_cols=create_data.get("canvas_cols", 20),
            canvas_rows=create_data.get("canvas_rows", 20),
            edge_styles=create_data.get("edge_styles", {}),
            sort_order=Zone.objects.filter(restaurant_id=restaurant_id).count(),
        )
        zone_id_map[zone_client_id] = str(created_zone.public_id)

    # ------------------------------------------------------------------
    # 2. Remap client-generated zone IDs to server zone IDs in all entity
    #    lists so tables/obstacles/thresholds/portals reference real zones.
    # ------------------------------------------------------------------
    for entity_list_name in ("tables", "obstacles", "thresholds", "portals"):
        for entity in layout_data.get(entity_list_name, []):
            zid = entity.get("zone_id")
            if zid and str(zid) in zone_id_map:
                entity["zone_id"] = zone_id_map[str(zid)]
            if entity_list_name == "portals":
                tzid = entity.get("target_zone_id")
                if tzid and str(tzid) in zone_id_map:
                    entity["target_zone_id"] = zone_id_map[str(tzid)]

    # ------------------------------------------------------------------
    # 3. Zone updates (name, canvas cols/rows, edge styles).
    # ------------------------------------------------------------------
    for update_data in zones_data.get("updated", []):
        zone = Zone.objects.filter(public_id=update_data["public_id"], restaurant_id=restaurant_id).first()
        if zone is None:
            continue
        changed = False
        for field in ("name", "canvas_cols", "canvas_rows", "edge_styles"):
            if field in update_data:
                setattr(zone, field, update_data[field])
                changed = True
        if changed:
            zone.save()

    existing_tables = {str(t.public_id): t for t in Table.objects.filter(restaurant_id=restaurant_id, active=True)}
    incoming_table_uuids: set[str] = set()
    table_id_map: dict[str, str] = {}
    public_number_map: dict[str, str] = {}

    for table_data in layout_data.get("tables", []):
        table_uuid = table_data.get("id")
        client_uuid = table_data.get("_client_id")
        public_number = table_data.get("public_number") or ""
        capacity = table_data["capacity"]
        zone_id = table_data.get("zone_id")
        zone = Zone.objects.filter(public_id=zone_id, restaurant_id=restaurant_id).first() if zone_id else None
        # Table.zone is non-nullable; a missing/stale zone_id is bad input, not a 500.
        if zone is None:
            raise ValidationError(f"Table references unknown zone_id {zone_id!r}.")

        existing = None
        client_id: str | None = None

        # 1. Match by UUID if provided and found in DB
        if table_uuid and str(table_uuid) in existing_tables:
            existing = existing_tables[str(table_uuid)]
            client_id = str(table_uuid)
        # 2. Fallback: match by public_number (handles missing/stale UUID)
        elif public_number:
            match = Table.objects.filter(restaurant_id=restaurant_id, public_number=public_number, active=True).first()
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

    # ------------------------------------------------------------------
    # 4. Zone deletions — deactivate any remaining active tables in the
    #    deleted zones (tables already moved to another zone were
    #    reassigned in step 1/2 and will not be caught here).
    # ------------------------------------------------------------------
    for zone_id in zones_data.get("deleted", []):
        zone = Zone.objects.filter(public_id=zone_id, restaurant_id=restaurant_id).first()
        if zone is None:
            continue
        for table in Table.objects.filter(zone=zone, active=True):
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
                    f"Zone '{zone.name}' has table {table.public_number} with active "
                    "reservations or sessions. Reassign before removing."
                )
            table.active = False
            table.save(update_fields=["active", "updated_at"])
        zone.delete()

    # Normalize UUID objects (zone_id, target_zone_id, ...) to strings before the
    # layout is written to the JSONField.
    layout_json = _to_jsonable(layout_data)

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

    # Clean up any residual draft after a successful publish so the editor
    # does not keep stale draft state around.
    from .models import LayoutDraft

    LayoutDraft.objects.filter(restaurant_id=restaurant_id, owner_id=published_by.pk).delete()

    return {
        "version": version,
        "table_id_map": table_id_map,
        "public_number_map": public_number_map,
        "zone_id_map": zone_id_map,
    }


<<<<<<< HEAD
@transaction.atomic
def save_draft(
    *,
    restaurant_id: int,
    draft_data: dict[str, Any],
    owner: User,
    base_version_id: uuid.UUID | None = None,
) -> LayoutDraft:
    from .models import LayoutDraft, LayoutVersion

    Restaurant.objects.select_for_update().get(pk=restaurant_id)
    current_version = LayoutVersion.objects.filter(restaurant_id=restaurant_id).order_by("-published_at", "-id").first()
    if (current_version is None and base_version_id is not None) or (
        current_version is not None and current_version.public_id != base_version_id
    ):
        raise LayoutVersionConflictError(str(current_version.public_id) if current_version else None)

    layout_json = _to_jsonable(draft_data)
    draft = LayoutDraft.objects.select_for_update().filter(restaurant_id=restaurant_id, owner=owner).first()
    if draft is None:
        draft = LayoutDraft.objects.create(
            restaurant_id=restaurant_id,
            owner=owner,
            base_version=current_version,
            draft_json=layout_json,
        )
    else:
        draft_version_id = draft.base_version.public_id if draft.base_version else None
        if draft_version_id != base_version_id:
            raise LayoutVersionConflictError(str(current_version.public_id) if current_version else None)
        draft.draft_json = layout_json
        draft.save(update_fields=["draft_json", "updated_at"])
    return draft


def delete_draft(*, restaurant_id: int, owner_id: int) -> bool:
    from .models import LayoutDraft

    deleted, _ = LayoutDraft.objects.filter(restaurant_id=restaurant_id, owner_id=owner_id).delete()
    return deleted > 0


def create_layout_entity_translation(
    *, layout_version_id: int, entity_id: str, language_code: str, label: str
) -> LayoutEntityTranslation:
    return LayoutEntityTranslation.objects.create(
        layout_version_id=layout_version_id,
        entity_id=entity_id,
        language_code=language_code,
        label=label,
    )


def update_layout_entity_translation(
    *, layout_version_id: int, entity_id: str, language_code: str, label: str
) -> LayoutEntityTranslation:
    translation = LayoutEntityTranslation.objects.get(
        layout_version_id=layout_version_id,
        entity_id=entity_id,
        language_code=language_code,
    )
    translation.label = label
    translation.save(update_fields=["label", "updated_at"])
    return translation


def delete_layout_entity_translation(
    *, layout_version_id: int, entity_id: str, language_code: str
) -> None:
    LayoutEntityTranslation.objects.filter(
        layout_version_id=layout_version_id,
        entity_id=entity_id,
        language_code=language_code,
    ).delete()


def get_layout_entity_translations(
    *, layout_version_id: int, language_code: str | None = None
) -> list[LayoutEntityTranslation]:
    qs = LayoutEntityTranslation.objects.filter(layout_version_id=layout_version_id)
    if language_code:
        qs = qs.filter(language_code=language_code)
    return list(qs)


def localize_layout_json(
    layout_json: dict[str, Any], language_code: str, layout_version_id: int
) -> dict[str, Any]:
    """Apply entity label translations to a layout JSON payload."""
    translations = LayoutEntityTranslation.objects.filter(
        layout_version_id=layout_version_id,
        language_code=language_code,
    )
    translation_map: dict[str, str] = {}
    for t in translations:
        translation_map[str(t.entity_id)] = t.label

    if not translation_map:
        return layout_json

    result = dict(layout_json)
    for entity_type in ("thresholds", "portals"):
        entities = result.get(entity_type, [])
        for entity in entities:
            eid = entity.get("id")
            if eid and str(eid) in translation_map:
                entity["label"] = translation_map[str(eid)]
    return result
