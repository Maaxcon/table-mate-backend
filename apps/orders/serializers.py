from django.db import models
from rest_framework import serializers

from .models import Order, OrderItem, Session, Ticket


class SessionSerializer(serializers.ModelSerializer[Session]):
    table: serializers.PrimaryKeyRelatedField[models.Model] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
    )
    reservation: serializers.PrimaryKeyRelatedField[models.Model] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
    )
    opened_by: serializers.PrimaryKeyRelatedField[models.Model] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
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
    session: serializers.PrimaryKeyRelatedField[Session] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
    )
    created_by: serializers.PrimaryKeyRelatedField[models.Model] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
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
    session: serializers.PrimaryKeyRelatedField[Session] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
    )
    order: serializers.PrimaryKeyRelatedField[Order] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
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
    order: serializers.PrimaryKeyRelatedField[Order] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
    )
    ticket: serializers.PrimaryKeyRelatedField[Ticket] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
    )
    menu_item: serializers.PrimaryKeyRelatedField[models.Model] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
    )
    voided_by: serializers.PrimaryKeyRelatedField[models.Model] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
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
