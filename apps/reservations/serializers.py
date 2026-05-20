from rest_framework import serializers

from apps.authentication.models import User
from apps.restaurants.models import Restaurant, Table

from .models import Reservation


class ReservationSerializer(serializers.ModelSerializer[Reservation]):
    restaurant: serializers.SlugRelatedField[Restaurant] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )
    customer: serializers.SlugRelatedField[User] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )
    table: serializers.SlugRelatedField[Table] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )

    class Meta:
        model = Reservation
        fields = [
            "public_id",
            "restaurant",
            "customer",
            "table",
            "guest_count",
            "start_at",
            "end_at",
            "status",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]
