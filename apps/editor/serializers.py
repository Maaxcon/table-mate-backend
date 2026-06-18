from typing import Any

from rest_framework import serializers

from apps.authentication.models import User
from apps.restaurants.models import Restaurant, Table, Zone
from common.api import PublicIdRelatedField

from .models import Layout, LayoutVersion


class LayoutSerializer(serializers.ModelSerializer[Layout]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    published_by: PublicIdRelatedField[User] = PublicIdRelatedField(read_only=True)

    class Meta:
        model = Layout
        fields = [
            "public_id",
            "restaurant",
            "version",
            "payload",
            "published_at",
            "published_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class EditorTableSerializer(serializers.ModelSerializer[Table]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    zone: PublicIdRelatedField[Zone] = PublicIdRelatedField(read_only=True, allow_null=True)

    class Meta:
        model = Table
        fields = [
            "public_id",
            "restaurant",
            "zone",
            "public_number",
            "capacity",
            "shape",
            "active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "public_id",
            "restaurant",
            "zone",
            "public_number",
            "capacity",
            "created_at",
            "updated_at",
        ]


# ---------------------------------------------------------------------------
# Layout JSON entity validators (Phase 2)
# ---------------------------------------------------------------------------

_VALID_TABLE_WIDTHS = {74, 120, 180, 240}
_VALID_TABLE_HEIGHTS = {74, 120, 180, 240}


class TableEntitySerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField(required=False, allow_null=True, default=None)
    public_number = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    x = serializers.IntegerField(min_value=0)
    y = serializers.IntegerField(min_value=0)
    width = serializers.IntegerField(min_value=1)
    height = serializers.IntegerField(min_value=1)
    rotation = serializers.IntegerField(min_value=0, max_value=359, default=0)
    shape = serializers.ChoiceField(choices=["rectangle", "round", "square", "booth"])
    capacity = serializers.IntegerField(min_value=1, max_value=20)
    zone_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    tags = serializers.ListField(child=serializers.CharField(), required=False, default=list)

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        shape = data.get("shape")
        w = data.get("width")
        h = data.get("height")

        if shape == "round":
            if w != h:
                raise serializers.ValidationError({"width": "Round tables must have equal width and height."})
            if w not in _VALID_TABLE_WIDTHS:
                raise serializers.ValidationError(
                    {"width": f"Round table width must be one of {_VALID_TABLE_WIDTHS}."}
                )
        else:
            if w not in _VALID_TABLE_WIDTHS:
                raise serializers.ValidationError(
                    {"width": f"Table width must be one of {_VALID_TABLE_WIDTHS}."}
                )
            if h not in _VALID_TABLE_HEIGHTS:
                raise serializers.ValidationError(
                    {"height": f"Table height must be one of {_VALID_TABLE_HEIGHTS}."}
                )
        return data


class ObstacleEntitySerializer(serializers.Serializer[Any]):
    x = serializers.IntegerField(min_value=0)
    y = serializers.IntegerField(min_value=0)
    width = serializers.IntegerField(min_value=1)
    height = serializers.IntegerField(min_value=1)
    rotation = serializers.IntegerField(min_value=0, max_value=359, default=0)


class ThresholdEntitySerializer(serializers.Serializer[Any]):
    x = serializers.IntegerField(min_value=0)
    y = serializers.IntegerField(min_value=0)
    width = serializers.IntegerField(min_value=1)
    height = serializers.IntegerField(min_value=1)


class PortalEntitySerializer(serializers.Serializer[Any]):
    x = serializers.IntegerField(min_value=0)
    y = serializers.IntegerField(min_value=0)
    width = serializers.IntegerField(min_value=1)
    height = serializers.IntegerField(min_value=1)
    target_zone_id = serializers.UUIDField()
    label = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class PublishLayoutSerializer(serializers.Serializer[Any]):
    tables = TableEntitySerializer(many=True, required=False, default=list)
    obstacles = ObstacleEntitySerializer(many=True, required=False, default=list)
    thresholds = ThresholdEntitySerializer(many=True, required=False, default=list)
    portals = PortalEntitySerializer(many=True, required=False, default=list)


class LayoutVersionSerializer(serializers.ModelSerializer[LayoutVersion]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    published_by: PublicIdRelatedField[User] = PublicIdRelatedField(read_only=True)

    class Meta:
        model = LayoutVersion
        fields = [
            "public_id",
            "restaurant",
            "parent_version",
            "layout_json",
            "published_at",
            "published_by",
            "created_at",
        ]
        read_only_fields = fields
