from datetime import datetime

from rest_framework import serializers

from apps.authentication.models import User
from apps.restaurants.models import Restaurant, Table
from common.api import PublicIdRelatedField, get_restaurant_id_from_auth

from .models import Reservation, ReservationStatus


class TableInfoSerializer(serializers.ModelSerializer[Table]):
    class Meta:
        model = Table
        fields = [
            "public_id",
            "table_number",
            "capacity",
            "shape",
        ]


class RestaurantInfoSerializer(serializers.ModelSerializer[Restaurant]):
    class Meta:
        model = Restaurant
        fields = [
            "public_id",
            "name",
        ]


class ReservationSerializer(serializers.ModelSerializer[Reservation]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    customer: PublicIdRelatedField[User] = PublicIdRelatedField(read_only=True)
    table: PublicIdRelatedField[Table] = PublicIdRelatedField(
        queryset=Table.objects.all(),
        required=True,
    )
    table_info = TableInfoSerializer(source="table", read_only=True)
    restaurant_info = RestaurantInfoSerializer(source="restaurant", read_only=True)
    customer_name = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = [
            "public_id",
            "restaurant",
            "customer",
            "table",
            "table_info",
            "restaurant_info",
            "customer_name",
            "type",
            "guest_count",
            "start_at",
            "end_at",
            "status",
            "created_by_staff",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "public_id",
            "restaurant",
            "customer",
            "customer_name",
            "created_at",
            "updated_at",
        ]

    def get_customer_name(self, obj: Reservation) -> str:
        if obj.customer:
            return f"{obj.customer.first_name} {obj.customer.last_name}".strip() or obj.customer.email
        return "Guest"

    def validate_table(self, value: Table) -> Table:
        request = self.context.get("request")
        restaurant_id = get_restaurant_id_from_auth(request) if request else None
        if restaurant_id is not None and value.restaurant_id != restaurant_id:
            raise serializers.ValidationError("Table does not belong to this restaurant.")
        return value

    def validate_guest_count(self, value: int) -> int:
        if self.instance is not None:
            capacity = self.instance.table.capacity if self.instance.table else None
        elif "table" in self.initial_data:
            try:
                table_obj = Table.objects.get(public_id=self.initial_data["table"])
                capacity = table_obj.capacity
            except Table.DoesNotExist:
                capacity = None
        else:
            capacity = None
        if capacity is not None and value > capacity:
            raise serializers.ValidationError(f"Guest count exceeds table capacity ({capacity}).")
        return value

    def validate_status(self, value: str) -> str:
        if value == ReservationStatus.CANCELLED:
            return value
        raise serializers.ValidationError("Only cancellation is allowed.")

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        start_at = attrs.get("start_at")
        end_at = attrs.get("end_at")
        if isinstance(start_at, datetime) and isinstance(end_at, datetime) and start_at >= end_at:
            raise serializers.ValidationError({"end_at": "end_at must be after start_at."})
        return attrs
