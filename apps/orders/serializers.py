from typing import Any

from rest_framework import serializers

from apps.authentication.models import User
from apps.menu.models import MenuItem
from apps.reservations.models import Reservation
from apps.restaurants.models import Restaurant, Table
from common.api import PublicIdRelatedField

from .models import Order, OrderItem, Session, Ticket


class SessionSerializer(serializers.ModelSerializer[Session]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    table: PublicIdRelatedField[Table] = PublicIdRelatedField(read_only=True)
    reservation: PublicIdRelatedField[Reservation] = PublicIdRelatedField(
        read_only=True,
    )
    opened_by: PublicIdRelatedField[User] = PublicIdRelatedField(read_only=True)

    class Meta:
        model = Session
        fields = [
            "public_id",
            "restaurant",
            "table",
            "reservation",
            "opened_by",
            "guest_count",
            "status",
            "currency",
            "running_total",
            "final_total",
            "started_at",
            "closed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class OrderSerializer(serializers.ModelSerializer[Order]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    session: PublicIdRelatedField[Session] = PublicIdRelatedField(read_only=True)
    created_by: PublicIdRelatedField[User] = PublicIdRelatedField(read_only=True)

    class Meta:
        model = Order
        fields = [
            "public_id",
            "restaurant",
            "session",
            "created_by",
            "created_by_source",
            "source",
            "status",
            "payment_status",
            "currency",
            "total_amount",
            "tax_total",
            "discount_total",
            "tip_total",
            "service_charge",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class TicketSerializer(serializers.ModelSerializer[Ticket]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    session: PublicIdRelatedField[Session] = PublicIdRelatedField(read_only=True)
    order: PublicIdRelatedField[Order] = PublicIdRelatedField(read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "public_id",
            "restaurant",
            "session",
            "order",
            "status",
            "injected_at",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class CreateOrderItemSerializer(serializers.Serializer[None]):
    menu_item_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    guest_slot = serializers.IntegerField(min_value=0)
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class CreateOrderFromCartSerializer(serializers.Serializer[None]):
    table_id = serializers.UUIDField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    items = CreateOrderItemSerializer(many=True, allow_empty=False)

    def validate_items(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        return value

    def validate_table_id(self, value: str) -> str:
        return str(value)


class OrderItemSerializer(serializers.ModelSerializer[OrderItem]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    order: PublicIdRelatedField[Order] = PublicIdRelatedField(read_only=True)
    ticket: PublicIdRelatedField[Ticket] = PublicIdRelatedField(read_only=True)
    menu_item: PublicIdRelatedField[MenuItem] = PublicIdRelatedField(read_only=True)
    voided_by: PublicIdRelatedField[User] = PublicIdRelatedField(read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "public_id",
            "restaurant",
            "order",
            "ticket",
            "menu_item",
            "guest_slot",
            "quantity",
            "comment",
            "modifiers",
            "status",
            "unit_price",
            "total_price",
            "tax_rate",
            "tax_amount",
            "voided_at",
            "voided_by",
            "void_reason",
            "is_wasted",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]
