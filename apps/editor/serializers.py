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
            "table_number",
            "capacity",
            "shape",
            "active",
            "position_x",
            "position_y",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "public_id",
            "restaurant",
            "zone",
            "table_number",
            "capacity",
            "created_at",
            "updated_at",
        ]


class PublishLayoutSerializer(serializers.Serializer[Any]):
    layout_json = serializers.JSONField()


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
