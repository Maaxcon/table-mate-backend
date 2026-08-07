from __future__ import annotations

import uuid
from typing import Any

from rest_framework import serializers


class GetMenuArgsSerializer(serializers.Serializer):
    query = serializers.CharField(required=False, allow_blank=True, max_length=255)
    category_id = serializers.CharField(required=False, allow_blank=True, max_length=64)
    available_only = serializers.BooleanField(required=False, default=False)
    language = serializers.CharField(required=False, allow_blank=True, max_length=16)


class GetRestaurantInfoArgsSerializer(serializers.Serializer):
    topic = serializers.ChoiceField(
        required=False,
        choices=["hours", "address", "policy", "payment", "contact"],
        allow_blank=False,
    )


class CheckAvailabilityArgsSerializer(serializers.Serializer):
    date = serializers.DateField()
    time = serializers.TimeField(format="%H:%M")
    party_size = serializers.IntegerField(min_value=1, max_value=50)


class CreateReservationArgsSerializer(serializers.Serializer):
    date = serializers.DateField()
    time = serializers.TimeField(format="%H:%M")
    party_size = serializers.IntegerField(min_value=1, max_value=50)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)
    table_id = serializers.CharField(required=False, allow_blank=True, max_length=64)


class RescheduleReservationArgsSerializer(serializers.Serializer):
    reservation_id = serializers.CharField()
    date = serializers.DateField(required=False)
    time = serializers.TimeField(format="%H:%M", required=False)
    party_size = serializers.IntegerField(required=False, min_value=1, max_value=50)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not any(key in attrs for key in ("date", "time", "party_size")):
            raise serializers.ValidationError("Provide at least one of date, time or party_size.")
        return attrs


class CancelReservationArgsSerializer(serializers.Serializer):
    reservation_id = serializers.CharField()
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class ModifierSelectionSerializer(serializers.Serializer):
    modifier_id = serializers.UUIDField()
    option_id = serializers.UUIDField()


class AddToCartArgsSerializer(serializers.Serializer):
    menu_item_id = serializers.CharField()
    quantity = serializers.IntegerField(min_value=1, max_value=100, default=1)
    modifiers = serializers.ListField(
        required=False,
        default=list,
        child=ModifierSelectionSerializer(),
    )
    guest_comment = serializers.CharField(required=False, allow_blank=True, max_length=500)


class GetFloorStatusArgsSerializer(serializers.Serializer):
    pass


class ReplyOutputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["reply"])
    text = serializers.CharField(min_length=1, max_length=2000)


class ToolCallOutputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["tool_call"])
    tool = serializers.CharField(min_length=1, max_length=64)
    arguments = serializers.JSONField(default=dict)


def validate_model_output(data: Any) -> dict[str, Any]:
    """Validate the model's JSON envelope. Raises on any malformed shape.

    Accepts ``{"kind": "reply", "text": ...}`` or
    ``{"kind": "tool_call", "tool": ..., "arguments": {...}}``.
    """
    if not isinstance(data, dict):
        raise serializers.ValidationError("Model output must be a JSON object.")

    kind = data.get("kind")
    if kind == "reply":
        serializer = ReplyOutputSerializer(data=data)
    elif kind == "tool_call":
        serializer = ToolCallOutputSerializer(data=data)
    else:
        raise serializers.ValidationError("Model output must declare kind 'reply' or 'tool_call'.")

    serializer.is_valid(raise_exception=True)
    validated = serializer.validated_data

    if kind == "tool_call":
        tool = str(validated["tool"])
        arguments = validated.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise serializers.ValidationError("Tool arguments must be an object.")
        if not tool:
            raise serializers.ValidationError("Tool name must not be empty.")

    return validated


def validate_tool_args(tool: str, arguments: Any) -> dict[str, Any]:
    """Validate tool arguments against the registered schema for ``tool``."""
    from .registry import registry

    if not isinstance(arguments, dict):
        raise serializers.ValidationError("Tool arguments must be an object.")
    serializer_cls = registry.schema_for(tool)
    if serializer_cls is None:
        raise serializers.ValidationError(f"Unknown tool: {tool}")
    serializer = serializer_cls(data=arguments)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


__all__ = [
    "AddToCartArgsSerializer",
    "CancelReservationArgsSerializer",
    "CheckAvailabilityArgsSerializer",
    "CreateReservationArgsSerializer",
    "GetFloorStatusArgsSerializer",
    "GetMenuArgsSerializer",
    "GetRestaurantInfoArgsSerializer",
    "RescheduleReservationArgsSerializer",
    "validate_model_output",
    "validate_tool_args",
]
