from rest_framework import serializers

from apps.authentication.models import User
from apps.menu.models import MenuItem
from apps.reservations.models import Reservation
from apps.restaurants.models import Restaurant, Table
from common.api import PublicIdRelatedField

from .models import Order, OrderItem, Session, Ticket


class SessionSerializer(serializers.ModelSerializer[Session]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    table: PublicIdRelatedField[Table] = PublicIdRelatedField(
        queryset=Table.objects.all(),
    )
    reservation: PublicIdRelatedField[Reservation] = PublicIdRelatedField(
        queryset=Reservation.objects.all(),
        allow_null=True,
        required=False,
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
        read_only_fields = ["public_id", "restaurant", "opened_by", "created_at", "updated_at"]


class OrderSerializer(serializers.ModelSerializer[Order]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    session: PublicIdRelatedField[Session] = PublicIdRelatedField(
        queryset=Session.objects.all(),
    )
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
        read_only_fields = ["public_id", "restaurant", "created_by", "created_at", "updated_at"]


class TicketSerializer(serializers.ModelSerializer[Ticket]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    session: PublicIdRelatedField[Session] = PublicIdRelatedField(
        queryset=Session.objects.all(),
    )
    order: PublicIdRelatedField[Order] = PublicIdRelatedField(
        queryset=Order.objects.all(),
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
        read_only_fields = ["public_id", "restaurant", "created_at", "updated_at"]


class OrderItemSerializer(serializers.ModelSerializer[OrderItem]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    order: PublicIdRelatedField[Order] = PublicIdRelatedField(
        queryset=Order.objects.all(),
    )
    ticket: PublicIdRelatedField[Ticket] = PublicIdRelatedField(
        queryset=Ticket.objects.all(),
        allow_null=True,
        required=False,
    )
    menu_item: PublicIdRelatedField[MenuItem] = PublicIdRelatedField(
        queryset=MenuItem.objects.all(),
    )
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
        read_only_fields = ["public_id", "restaurant", "created_at", "updated_at"]
