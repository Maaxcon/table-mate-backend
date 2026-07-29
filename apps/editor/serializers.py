from typing import Any

from django.core.validators import MaxValueValidator
from rest_framework import serializers

from apps.authentication.models import User
from apps.menu.services.localization import get_localized_content
from apps.restaurants.models import Restaurant, Table, Zone
from common.api import PublicIdRelatedField

from .models import Layout, LayoutVersion
from .services import localize_layout_json

GRID = 100
DEFAULT_CANVAS_COLS = 20
DEFAULT_CANVAS_ROWS = 20


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
    _lang = serializers.SerializerMethodField(read_only=True)
    _is_fallback = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Table
        fields = [
            "public_id",
            "restaurant",
            "zone",
            "public_number",
            "capacity",
            "active",
            "_lang",
            "_is_fallback",
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

    def get__lang(self, obj: Table) -> str | None:
        request = self.context.get("request")
        return getattr(request, "active_language", None) if request else None

    def get__is_fallback(self, obj: Table) -> bool:
        request = self.context.get("request")
        return getattr(request, "active_language_is_fallback", False) if request else False

    def to_representation(self, instance: Table) -> dict[str, Any]:
        data = super().to_representation(instance)
        request = self.context.get("request")
        lang = getattr(request, "active_language", None) if request else None
        if lang:
            localized = get_localized_content(instance, lang)
            if "public_number" in localized and localized["public_number"] is not None:
                data["public_number"] = localized["public_number"]
        return data


# ---------------------------------------------------------------------------
# Layout JSON entity validators (Phase 2)
# ---------------------------------------------------------------------------


class RotationField(serializers.IntegerField):
    """Degrees, normalized to [0, 360) rather than bounds-checked.

    A plain IntegerField(max_value=359) is asymmetric — it rejects 360 (the
    same angle as 0) while happily accepting an unbounded negative like
    -1000000, since there's no min_value. Normalizing via modulo sidesteps
    picking an arbitrary lower bound entirely: any integer input maps to its
    canonical angle instead of being rejected or stored un-normalized.
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("default", 0)
        kwargs.pop("min_value", None)
        kwargs.pop("max_value", None)
        super().__init__(**kwargs)

    def to_internal_value(self, data: Any) -> int:
        value: int = super().to_internal_value(data)
        return value % 360


class TableEntitySerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField(required=False, allow_null=True, default=None)
    # Opaque client-side correlation handle for newly-added entities (not yet persisted).
    # The frontend mints a throwaway local id; the backend never parses it as a UUID, it only
    # echoes it back in table_id_map / public_number_map so the client can reconcile after publish.
    # Hence a free-form string, not a UUIDField.
    _client_id = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)
    public_number = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    x = serializers.IntegerField(min_value=-100)
    y = serializers.IntegerField(min_value=-100)
    width = serializers.IntegerField(min_value=1)
    height = serializers.IntegerField(min_value=1)
    rotation = RotationField()
    shape = serializers.ChoiceField(choices=["rectangle", "round", "square", "booth"])
    capacity = serializers.IntegerField(min_value=1, max_value=20)
    zone_id = serializers.UUIDField()
    tags = serializers.ListField(child=serializers.CharField(), required=False, default=list)

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        shape = data.get("shape")
        w = data.get("width")
        h = data.get("height")

        if shape == "round" and w != h:
            raise serializers.ValidationError({"width": "Round tables must have equal width and height."})
        return data


class ObstacleEntitySerializer(serializers.Serializer[Any]):
    x = serializers.IntegerField(min_value=-100)
    y = serializers.IntegerField(min_value=-100)
    width = serializers.IntegerField(min_value=1)
    height = serializers.IntegerField(min_value=1)
    rotation = RotationField()
    zone_id = serializers.UUIDField()


class ThresholdEntitySerializer(serializers.Serializer[Any]):
    x = serializers.IntegerField(min_value=-100)
    y = serializers.IntegerField(min_value=-100)
    width = serializers.IntegerField(min_value=1)
    height = serializers.IntegerField(min_value=1)
    rotation = RotationField()
    threshold_label = serializers.CharField(max_length=64, required=False, allow_blank=True, default="", source="label")
    zone_id = serializers.UUIDField()


class PortalEntitySerializer(serializers.Serializer[Any]):
    x = serializers.IntegerField(min_value=-100)
    y = serializers.IntegerField(min_value=-100)
    width = serializers.IntegerField(min_value=1)
    height = serializers.IntegerField(min_value=1)
    rotation = RotationField()
    target_zone_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    portal_label = serializers.CharField(max_length=64, required=False, allow_blank=True, default="", source="label")
    zone_id = serializers.UUIDField()


class ZoneCreateSerializer(serializers.Serializer[Any]):
    _client_id = serializers.UUIDField()
    name = serializers.CharField(max_length=128)
    canvas_cols = serializers.IntegerField(min_value=8, max_value=50, default=DEFAULT_CANVAS_COLS)
    canvas_rows = serializers.IntegerField(min_value=8, max_value=50, default=DEFAULT_CANVAS_ROWS)
    edge_styles = serializers.JSONField(default=dict)


class ZoneUpdateSerializer(serializers.Serializer[Any]):
    public_id = serializers.UUIDField()
    name = serializers.CharField(max_length=128, required=False)
    canvas_cols = serializers.IntegerField(min_value=8, max_value=50, required=False)
    canvas_rows = serializers.IntegerField(min_value=8, max_value=50, required=False)
    edge_styles = serializers.JSONField(required=False)


class PendingZoneSerializer(serializers.Serializer[Any]):
    created = ZoneCreateSerializer(many=True, required=False, default=list)
    updated = ZoneUpdateSerializer(many=True, required=False, default=list)
    deleted = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)


class PublishLayoutSerializer(serializers.Serializer[Any]):
    # The editor sends the published layout version it started from. A null
    # value is valid only when the restaurant has no published layout yet.
    base_layout_version_id = serializers.UUIDField(allow_null=True)
    canvas_cols = serializers.IntegerField(min_value=8, max_value=50, required=False, default=DEFAULT_CANVAS_COLS)
    canvas_rows = serializers.IntegerField(min_value=8, max_value=50, required=False, default=DEFAULT_CANVAS_ROWS)
    tables = TableEntitySerializer(many=True, required=False, default=list)
    obstacles = ObstacleEntitySerializer(many=True, required=False, default=list)
    thresholds = ThresholdEntitySerializer(many=True, required=False, default=list)
    portals = PortalEntitySerializer(many=True, required=False, default=list)
    deleted_table_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    zones = PendingZoneSerializer(required=False)

    def _apply_canvas_limits(self, canvas_cols: int, canvas_rows: int) -> None:
        """Inject MaxValueValidator limits derived from canvas dimensions into child entity fields."""
        cw = canvas_cols * GRID
        ch = canvas_rows * GRID

        # Per-entity-type field limits: (field_name, x_max, y_max, w_max, h_max)
        limits: dict[str, dict[str, int]] = {
            "tables": {"x": cw - 2 * GRID, "y": ch - 2 * GRID, "width": cw, "height": ch},
            "obstacles": {"x": cw - 2 * GRID, "y": ch - GRID, "width": cw, "height": ch},
            "thresholds": {"x": cw, "y": ch, "width": cw, "height": ch},
            "portals": {"x": cw, "y": ch, "width": cw, "height": ch},
        }

        for field_name, field_limits in limits.items():
            list_field = self.fields.get(field_name)
            if not list_field:
                continue
            child = getattr(list_field, "child", None)
            if not child:
                continue
            for fname, max_val in field_limits.items():
                f = child.fields.get(fname)
                if not f:
                    continue
                # Replace existing MaxValueValidator or append a new one
                for v in f.validators:
                    if isinstance(v, MaxValueValidator):
                        v.limit_value = max_val
                        break
                else:
                    f.validators.append(MaxValueValidator(max_val))

    def to_internal_value(self, data: dict[str, Any]) -> dict[str, Any]:
        canvas_cols = data.get("canvas_cols", DEFAULT_CANVAS_COLS)
        canvas_rows = data.get("canvas_rows", DEFAULT_CANVAS_ROWS)
        try:
            canvas_cols = int(canvas_cols)
        except (TypeError, ValueError):
            canvas_cols = DEFAULT_CANVAS_COLS
        try:
            canvas_rows = int(canvas_rows)
        except (TypeError, ValueError):
            canvas_rows = DEFAULT_CANVAS_ROWS
        canvas_cols = max(8, min(50, canvas_cols))
        canvas_rows = max(8, min(50, canvas_rows))
        self._apply_canvas_limits(canvas_cols, canvas_rows)
        result: dict[str, Any] = super().to_internal_value(data)
        return result


class DraftLayoutSerializer(serializers.Serializer[Any]):
    draft_json = PublishLayoutSerializer(required=False, allow_null=True)
    is_draft = serializers.BooleanField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    owner_id = serializers.CharField(read_only=True, allow_null=True, default=None)


class LayoutEntityTranslationSerializer(serializers.Serializer[Any]):
    entity_id = serializers.UUIDField()
    language_code = serializers.CharField(max_length=10)
    entity_label = serializers.CharField(max_length=255, source="label")

    class Meta:
        fields = ["entity_id", "language_code", "entity_label"]


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

    def to_representation(self, instance: LayoutVersion) -> dict[str, Any]:
        data = super().to_representation(instance)
        request = self.context.get("request")
        lang = getattr(request, "active_language", None) if request else None
        if lang and instance.layout_json:
            data["layout_json"] = localize_layout_json(instance.layout_json, lang, instance.pk)
        return data
