from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from apps.restaurants.models import Table
from common.hall_events import emit_hall_layout_published

if TYPE_CHECKING:
    from apps.authentication.models import User

    from .models import LayoutVersion


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


def publish_layout(
    *,
    restaurant_id: int,
    layout_json: dict[str, object],
    published_by: User,
    parent_version: LayoutVersion | None = None,
) -> LayoutVersion:
    from .models import LayoutVersion

    with transaction.atomic():
        if parent_version is None:
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
            )
        )
        return version
