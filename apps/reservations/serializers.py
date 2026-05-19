from django.db import models
from rest_framework import serializers

from .models import Reservation


class ReservationSerializer(serializers.ModelSerializer[Reservation]):
    customer: serializers.PrimaryKeyRelatedField[models.Model] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
    )
    table: serializers.PrimaryKeyRelatedField[models.Model] = (
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
