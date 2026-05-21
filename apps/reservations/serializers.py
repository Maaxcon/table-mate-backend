from rest_framework import serializers

from apps.authentication.models import User
from apps.restaurants.models import Restaurant, Table
from common.api import PublicIdRelatedField

from .models import Reservation


class ReservationSerializer(serializers.ModelSerializer[Reservation]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    customer: PublicIdRelatedField[User] = PublicIdRelatedField(read_only=True)
    table: PublicIdRelatedField[Table] = PublicIdRelatedField(read_only=True)

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
