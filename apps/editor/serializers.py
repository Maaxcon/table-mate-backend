from rest_framework import serializers

from apps.authentication.models import User
from apps.restaurants.models import Restaurant

from .models import Layout


class LayoutSerializer(serializers.ModelSerializer[Layout]):
    restaurant: serializers.SlugRelatedField[Restaurant] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )
    published_by: serializers.SlugRelatedField[User] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )

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
