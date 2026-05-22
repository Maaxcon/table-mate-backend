from rest_framework import serializers

from apps.authentication.models import User
from apps.restaurants.models import Restaurant, Table
from common.api import PublicIdRelatedField

from .models import Reservation


class ReservationSerializer(serializers.ModelSerializer[Reservation]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    customer: PublicIdRelatedField[User] = PublicIdRelatedField(read_only=True)
    table: PublicIdRelatedField[Table] = PublicIdRelatedField(
        queryset=Table.objects.all(),
        required=True,
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
        read_only_fields = [
            "public_id",
            "restaurant",
            "customer",
            "status",
            "created_at",
            "updated_at",
        ]

    def validate_table(self, value: Table) -> Table:
        request = self.context.get("request")
        if request and hasattr(request, "auth"):
            auth = request.auth
            restaurant_id = None
            if hasattr(auth, "get"):
                restaurant_id = auth.get("restaurant_id")
            if restaurant_id is not None and value.restaurant_id != int(restaurant_id):
                raise serializers.ValidationError("Table does not belong to this restaurant.")
        return value
