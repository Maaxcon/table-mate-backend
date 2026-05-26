from rest_framework import serializers

from apps.authentication.models import User
from apps.restaurants.models import Restaurant, Table
from common.api import PublicIdRelatedField, get_restaurant_id_from_auth

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
        restaurant_id = get_restaurant_id_from_auth(request) if request else None
        if restaurant_id is None:
            raise serializers.ValidationError("Restaurant context required.")
        if value.restaurant_id != restaurant_id:
            raise serializers.ValidationError("Table does not belong to this restaurant.")
        return value
