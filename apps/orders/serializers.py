from collections.abc import Mapping
from typing import Any

from rest_framework import serializers

from apps.authentication.models import User
from apps.menu.models import MenuItem
from apps.reservations.models import Reservation
from apps.restaurants.models import Restaurant, Table
from common.api import PublicIdRelatedField, get_restaurant_id_from_auth

from .models import Order, OrderItem, OrderItemStatus, Session, SessionStatus, Ticket, VoidReason


def _scope_to_request_restaurant(field: Any, context: Mapping[str, object]) -> None:
    request = context.get("request")
    if request is None:
        return
    restaurant_id = get_restaurant_id_from_auth(request)  # type: ignore[arg-type]
    if restaurant_id is not None and field.queryset is not None:
        field.queryset = field.queryset.filter(restaurant_id=restaurant_id)


class VoidReasonSerializer(serializers.ModelSerializer[VoidReason]):
    class Meta:
        model = VoidReason
        fields = ["code", "label"]
        read_only_fields = ["code", "label"]


class SessionSerializer(serializers.ModelSerializer[Session]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    table: PublicIdRelatedField[Table] = PublicIdRelatedField(
        queryset=Table.objects.all(),
    )
    reservation: PublicIdRelatedField[Reservation] = PublicIdRelatedField(read_only=True)
    opened_by: PublicIdRelatedField[User] = PublicIdRelatedField(read_only=True)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _scope_to_request_restaurant(self.fields["table"], self.context)

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
        read_only_fields = [
            "public_id",
            "restaurant",
            "opened_by",
            "subtotal",
            "tax",
            "total",
            "created_at",
            "updated_at",
        ]


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


_ORDER_ITEM_STATUS_TRANSITIONS: dict[str, set[str]] = {
    OrderItemStatus.PENDING: {OrderItemStatus.IN_PROGRESS},
    OrderItemStatus.IN_PROGRESS: {OrderItemStatus.READY},
    OrderItemStatus.READY: {OrderItemStatus.SERVED},
    OrderItemStatus.SERVED: set(),
    OrderItemStatus.VOIDED: set(),
}


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
    void_reason: serializers.SlugRelatedField[VoidReason] = serializers.SlugRelatedField(
        slug_field="code",
        read_only=True,
        allow_null=True,
    )
    menu_item_name = serializers.CharField(source="menu_item.name", read_only=True)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _scope_to_request_restaurant(self.fields["order"], self.context)
        _scope_to_request_restaurant(self.fields["ticket"], self.context)
        _scope_to_request_restaurant(self.fields["menu_item"], self.context)

    def validate_status(self, value: str) -> str:
        if self.instance is None:
            return value
        current = self.instance.status
        allowed = _ORDER_ITEM_STATUS_TRANSITIONS.get(current, set())
        if value not in allowed:
            raise serializers.ValidationError(
                f"Cannot transition from '{current}' to '{value}'. "
                f"Allowed transitions from '{current}': {', '.join(sorted(allowed)) or 'none'}."
            )
        if value == OrderItemStatus.VOIDED:
            raise serializers.ValidationError("Use the dedicated /void/ endpoint to void an order item.")
        return value

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
            "void_reason_note",
            "is_wasted",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "restaurant", "created_at", "updated_at"]


class CreateOrderItemSerializer(serializers.Serializer[None]):
    menu_item = PublicIdRelatedField[MenuItem](
        queryset=MenuItem.objects.all(),
        required=True,
    )
    guest_slot = serializers.IntegerField(required=False, default=1, min_value=1)
    quantity = serializers.IntegerField(required=False, default=1, min_value=1)
    comment = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _scope_to_request_restaurant(self.fields["menu_item"], self.context)


class CreateOrderSerializer(serializers.Serializer[None]):
    session = PublicIdRelatedField[Session](
        queryset=Session.objects.all(),
        required=True,
    )
    items = CreateOrderItemSerializer(many=True, required=True)

    def validate_session(self, value: Session) -> Session:
        if value.status != SessionStatus.OPEN:
            raise serializers.ValidationError("Session is not open.")
        return value

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _scope_to_request_restaurant(self.fields["session"], self.context)
