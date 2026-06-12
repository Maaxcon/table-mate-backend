from collections.abc import Mapping
from typing import Any

from rest_framework import serializers

from apps.authentication.models import User
from apps.menu.models import MenuItem
from apps.reservations.models import Reservation
from apps.restaurants.models import Restaurant, Table
from common.api import PublicIdRelatedField, get_restaurant_id_from_auth

from .models import Order, OrderItem, Session, Ticket


def _scope_to_request_restaurant(field: Any, context: Mapping[str, object]) -> None:
    request = context.get("request")
    if request is None:
        return
    restaurant_id = get_restaurant_id_from_auth(request)  # type: ignore[arg-type]
    if restaurant_id is not None and field.queryset is not None:
        field.queryset = field.queryset.filter(restaurant_id=restaurant_id)


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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _scope_to_request_restaurant(self.fields["table"], self.context)
        _scope_to_request_restaurant(self.fields["reservation"], self.context)

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
            "subtotal",
            "tax",
            "total",
            "opened_at",
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _scope_to_request_restaurant(self.fields["session"], self.context)

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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _scope_to_request_restaurant(self.fields["session"], self.context)
        _scope_to_request_restaurant(self.fields["order"], self.context)

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
    menu_item_name = serializers.CharField(source="menu_item.name", read_only=True)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _scope_to_request_restaurant(self.fields["order"], self.context)
        _scope_to_request_restaurant(self.fields["ticket"], self.context)
        _scope_to_request_restaurant(self.fields["menu_item"], self.context)

    class Meta:
        model = OrderItem
        fields = [
            "public_id",
            "restaurant",
            "order",
            "ticket",
            "menu_item",
            "menu_item_name",
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
