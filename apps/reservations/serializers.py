from datetime import datetime, timedelta

from django.utils import timezone
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
            "public_number",
            "capacity",
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
    # Actuals of the seated party (from the OPEN session), annotated by the viewset.
    # Null for pending/unseated reservations or in contexts without the annotation.
    opened_at = serializers.SerializerMethodField()
    session_ends_at = serializers.SerializerMethodField()
    session_table = serializers.SerializerMethodField()
    session_table_number = serializers.SerializerMethodField()
    has_preorder = serializers.SerializerMethodField()
    preorder_cooking = serializers.SerializerMethodField()
    preorder_ready = serializers.SerializerMethodField()

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
            "guest_name",
            "type",
            "guest_count",
            "start_at",
            "end_at",
            "opened_at",
            "session_ends_at",
            "session_table",
            "session_table_number",
            "has_preorder",
            "preorder_cooking",
            "preorder_ready",
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
            "opened_at",
            "session_ends_at",
            "session_table",
            "session_table_number",
            "has_preorder",
            "preorder_cooking",
            "preorder_ready",
            "created_at",
            "updated_at",
        ]

    def get_opened_at(self, obj: Reservation) -> str | None:
        val = getattr(obj, "session_opened_at", None)
        return val.isoformat() if val else None

    def get_session_ends_at(self, obj: Reservation) -> str | None:
        val = getattr(obj, "session_ends_at", None)
        return val.isoformat() if val else None

    def get_session_table(self, obj: Reservation) -> str | None:
        val = getattr(obj, "session_table_id", None)
        return str(val) if val else None

    def get_session_table_number(self, obj: Reservation) -> str | None:
        return getattr(obj, "session_table_number", None)

    def get_has_preorder(self, obj: Reservation) -> bool:
        return bool(getattr(obj, "has_preorder", False))

    def get_preorder_cooking(self, obj: Reservation) -> bool:
        return bool(getattr(obj, "preorder_cooking", False))

    def get_preorder_ready(self, obj: Reservation) -> bool:
        return bool(getattr(obj, "preorder_ready", False))

    def get_customer_name(self, obj: Reservation) -> str:
        if obj.guest_name:
            return obj.guest_name
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
        if value < 1:
            raise serializers.ValidationError("Guest count must be at least 1.")
        request = self.context.get("request")
        user = getattr(request, "user", None)
        is_staff = getattr(user, "role", None) in ("admin", "waiter")
        if is_staff:
            return value
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
        if value in ReservationStatus.values:
            return value
        raise serializers.ValidationError(f"Invalid status: {value}.")

    def validate_notes(self, value: str) -> str:
        if len(value) > 2000:
            raise serializers.ValidationError("Notes must be at most 2000 characters.")
        return value

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        start_at = attrs.get("start_at")
        end_at = attrs.get("end_at")
        if isinstance(start_at, datetime) and isinstance(end_at, datetime):
            if start_at >= end_at:
                raise serializers.ValidationError({"end_at": "end_at must be after start_at."})
            if start_at < timezone.now():
                raise serializers.ValidationError({"start_at": "start_at must be in the future."})
            if end_at - start_at > timedelta(hours=8):
                raise serializers.ValidationError({"end_at": "Duration must not exceed 8 hours."})
        return attrs


class BatchUpdateItemSerializer(serializers.Serializer[dict[str, object]]):
    reservation_id = serializers.UUIDField()
    new_table_id = serializers.UUIDField()
    new_date = serializers.DateField()
    new_start_time = serializers.TimeField()
    new_end_time = serializers.TimeField()

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        return attrs


class BatchUpdateSerializer(serializers.Serializer[dict[str, object]]):
    changes = BatchUpdateItemSerializer(many=True)
    cancellations = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )


class BatchUpdateErrorSerializer(serializers.Serializer[dict[str, object]]):
    detail = serializers.CharField()
    code = serializers.CharField(required=False)
    conflicting_reservation_id = serializers.CharField(required=False)


class PreorderItemSerializer(serializers.Serializer[dict[str, object]]):
    name = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price = serializers.CharField()
    total_price = serializers.CharField()


class PreorderDetailSerializer(serializers.Serializer[dict[str, object]]):
    """A reservation's paid pre-order rounds, combined into one check.

    Response-shape contract for the `preorder` action. Declared (and used to
    render) so the published schema matches what the endpoint actually
    returns — without it drf-spectacular falls back to the viewset's
    ReservationSerializer, and the generated clients are wrong.
    """

    order_id = serializers.CharField()
    currency = serializers.CharField()
    subtotal = serializers.CharField()
    tax = serializers.CharField()
    service_charge = serializers.CharField()
    total = serializers.CharField()
    can_cancel = serializers.BooleanField()
    items = PreorderItemSerializer(many=True)
