from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from apps.menu.models import MenuItem, ModifierOption
from common.exceptions import InvalidModifierError, ModifierRequiredError


def normalize_modifiers(menu_item: MenuItem, modifiers: Any) -> tuple[list[dict[str, Any]], Decimal]:
    """Validate and normalize ``add_to_cart`` modifier selections.

    Each selection is ``{"modifier_id": <group public_id>, "option_id": <option
    public_id>}``. Returns ``(snapshot, price_delta)`` where ``snapshot`` is a
    denormalized list suitable for JSON storage on a cart line. Raises
    :class:`InvalidModifierError` for unknown group/option ids and
    :class:`ModifierRequiredError` when a required group has no selection.
    """
    if not modifiers:
        modifiers = []
    if not isinstance(modifiers, list):
        raise InvalidModifierError("Modifiers must be a list.")

    groups = {str(g.public_id): g for g in menu_item.modifier_groups.all()}
    options = {
        str(o.public_id): o
        for o in ModifierOption.objects.filter(group__menu_item=menu_item)
    }

    snapshot: list[dict[str, Any]] = []
    selected_group_ids: set[str] = set()
    for entry in modifiers:
        if not isinstance(entry, dict):
            raise InvalidModifierError("Each modifier must be an object.")
        group_id = str(entry.get("modifier_id") or "")
        option_id = str(entry.get("option_id") or "")
        group = groups.get(group_id)
        if group is None:
            raise InvalidModifierError(f"Modifier group {group_id} does not belong to this item.")
        option = options.get(option_id)
        if option is None or option.group_id != group.pk:
            raise InvalidModifierError(f"Option {option_id} is not valid for modifier {group.name}.")
        selected_group_ids.add(group_id)
        snapshot.append(
            {
                "modifier_id": group_id,
                "option_id": option_id,
                "name": f"{group.name}: {option.name}",
                "price_delta": str(option.price_delta),
            }
        )

    required_missing = [
        {
            "modifier_id": str(g.public_id),
            "name": g.name,
            "options": [{"option_id": str(o.public_id), "name": o.name} for o in g.options.all()],
        }
        for g in menu_item.modifier_groups.filter(is_required=True)
        if str(g.public_id) not in selected_group_ids
    ]
    if required_missing:
        raise ModifierRequiredError(missing=required_missing)

    price_delta = sum((Decimal(item["price_delta"]) for item in snapshot), Decimal("0"))
    return snapshot, price_delta


def modifiers_key(snapshot: list[dict[str, Any]]) -> str:
    """Deterministic fingerprint of a normalized modifier snapshot."""
    canonical = sorted(
        ({"modifier_id": item["modifier_id"], "option_id": item["option_id"]} for item in snapshot),
        key=lambda item: (item["modifier_id"], item["option_id"]),
    )
    return hashlib.sha1(json.dumps(canonical, sort_keys=True).encode("utf-8"), usedforsecurity=False).hexdigest()


__all__ = ["modifiers_key", "normalize_modifiers"]
