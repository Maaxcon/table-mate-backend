from rest_framework import serializers

from apps.authentication.models import User
from apps.restaurants.models import Table

from .models import Reservation


class ReservationSerializer(serializers.ModelSerializer[Reservation]):
    customer: serializers.PrimaryKeyRelatedField[User] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
    )
    table: serializers.PrimaryKeyRelatedField[Table] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
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
