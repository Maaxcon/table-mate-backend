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
            "service_charge",
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
            "service_charge",
            "total",
            "currency",
            "opened_at",
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
    # `label` shadows Field.label in the stubs, but DRF resolves it from the
    # model property at runtime; the ignore is purely a typing concern.
    label = serializers.CharField(read_only=True)  # type: ignore[assignment]
    table_number = serializers.CharField(
        source="session.table.public_number",
        read_only=True,
    )
    server_name = serializers.SerializerMethodField()
    guest_count = serializers.IntegerField(
        source="session.guest_count",
        read_only=True,
    )
    items_count = serializers.SerializerMethodField()

    def get_server_name(self, obj: Ticket) -> str:
        annotated_name = getattr(obj, "server_name", None)
        if isinstance(annotated_name, str):
            trimmed = annotated_name.strip()
            if trimmed:
                return trimmed

        created_by = getattr(obj.order, "created_by", None)
        if isinstance(created_by, User):
            full_name = f"{created_by.first_name} {created_by.last_name}".strip()
            if full_name:
                return full_name
        return ""

    def get_items_count(self, obj: Ticket) -> int:
        annotated_count = getattr(obj, "items_count", None)
        if annotated_count is not None:
            try:
                return int(annotated_count)
            except (TypeError, ValueError):
                return 0
        return obj.items.exclude(status=OrderItemStatus.VOIDED).count()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _scope_to_request_restaurant(self.fields["session"], self.context)
        _scope_to_request_restaurant(self.fields["order"], self.context)

    class Meta:
        model = Ticket
        fields = [
            "public_id",
            "label",
            "daily_number",
            "restaurant",
            "session",
            "order",
            "status",
            "injected_at",
            "started_at",
            "completed_at",
            "table_number",
            "server_name",
            "guest_count",
            "items_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "public_id",
            "label",
            "daily_number",
            "restaurant",
            "table_number",
            "server_name",
            "guest_count",
            "items_count",
            "created_at",
            "updated_at",
        ]


class TicketStatsSerializer(serializers.Serializer[None]):
    avg_prep_time_seconds = serializers.FloatField(allow_null=True)


_ORDER_ITEM_STATUS_TRANSITIONS: dict[str, set[str]] = {
    OrderItemStatus.PENDING: {OrderItemStatus.IN_PROGRESS, OrderItemStatus.READY},
    OrderItemStatus.IN_PROGRESS: {OrderItemStatus.READY},
    OrderItemStatus.READY: {OrderItemStatus.SERVED, OrderItemStatus.PENDING},
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
    menu_item_category_id = serializers.UUIDField(
        source="menu_item.category.public_id",
        read_only=True,
        allow_null=True,
    )
    menu_item_category_name = serializers.CharField(
        source="menu_item.category.name",
        read_only=True,
        allow_null=True,
    )
    menu_item_category_color = serializers.CharField(
        source="menu_item.category.color",
        read_only=True,
        allow_null=True,
    )
    # Full amount owed for this line: goods + its tax + its service share.
    payable = serializers.DecimalField(max_digits=14, decimal_places=4, read_only=True)

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
            "menu_item_category_id",
            "menu_item_category_name",
            "menu_item_category_color",
            "guest_slot",
            "guest_display_name",
            "quantity",
            "comment",
            "modifiers",
            "status",
            "unit_price",
            "total_price",
            "tax_rate",
            "tax_amount",
            "payable",
            "is_paid",
            "voided_at",
            "voided_by",
            "void_reason",
            "void_reason_note",
            "is_wasted",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "restaurant", "created_at", "updated_at"]


class OrderItemVoidRequestSerializer(serializers.Serializer[None]):
    void_reason = serializers.CharField()
    note = serializers.CharField(required=False, allow_null=True, default=None)


class SessionPayRequestSerializer(serializers.Serializer[None]):
    # Omit (or send empty) to pay every outstanding item on the visit instead
    # of a specific selection.
    order_item_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
        default=list,
    )


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
        items_field = self.fields.get("items")
        if items_field is not None:
            child = getattr(items_field, "child", None)
            if child is not None:
                _scope_to_request_restaurant(child.fields["menu_item"], self.context)
