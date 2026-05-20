from rest_framework import serializers

from apps.authentication.models import User
from apps.menu.models import MenuItem
from apps.reservations.models import Reservation
from apps.restaurants.models import Restaurant, Table

from .models import Order, OrderItem, Session, Ticket


class SessionSerializer(serializers.ModelSerializer[Session]):
    restaurant: serializers.SlugRelatedField[Restaurant] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )
    table: serializers.SlugRelatedField[Table] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )
    reservation: serializers.SlugRelatedField[Reservation] = (
        serializers.SlugRelatedField(
            slug_field="public_id",
            read_only=True,
        )
    )
    opened_by: serializers.SlugRelatedField[User] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )

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
    restaurant: serializers.SlugRelatedField[Restaurant] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )
    session: serializers.SlugRelatedField[Session] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )
    created_by: serializers.SlugRelatedField[User] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )

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
    restaurant: serializers.SlugRelatedField[Restaurant] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )
    session: serializers.SlugRelatedField[Session] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )
    order: serializers.SlugRelatedField[Order] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )

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


class OrderItemSerializer(serializers.ModelSerializer[OrderItem]):
    restaurant: serializers.SlugRelatedField[Restaurant] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )
    order: serializers.SlugRelatedField[Order] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )
    ticket: serializers.SlugRelatedField[Ticket] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )
    menu_item: serializers.SlugRelatedField[MenuItem] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )
    voided_by: serializers.SlugRelatedField[User] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )

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
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]
