from typing import Any, cast

from rest_framework import serializers

from apps.authentication.models import User
from apps.menu.models import MenuItem
from apps.orders.models import CartItem, CartSession, OrderItem
from apps.reservations.models import Reservation
from apps.restaurants.models import Restaurant
from common.api import PublicIdRelatedField, get_restaurant_id_from_auth


class CartSessionSerializer(serializers.ModelSerializer[CartSession]):
    restaurant = PublicIdRelatedField[Restaurant](read_only=True)
    reservation = PublicIdRelatedField[Reservation](
        queryset=Reservation.objects.all(),
        required=True,
    )
    created_by = PublicIdRelatedField[User](read_only=True)
    participants = PublicIdRelatedField[User](
        many=True,
        read_only=True,
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None:
            restaurant_id = get_restaurant_id_from_auth(request)
            if restaurant_id is not None:
                field = cast(PublicIdRelatedField[Reservation], self.fields["reservation"])
                field.queryset = Reservation.objects.filter(
                    restaurant_id=restaurant_id,
                )

    class Meta:
        model = CartSession
        fields = [
            "public_id",
            "restaurant",
            "reservation",
            "status",
            "created_by",
            "participants",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "public_id",
            "restaurant",
            "status",
            "created_by",
            "created_at",
            "updated_at",
        ]


class CartMenuItemSnapshotSerializer(serializers.ModelSerializer[MenuItem]):
    """Just enough of the menu item to render a cart line on its own, so the
    cart never depends on which menu page/sort the client is currently showing."""

    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = MenuItem
        fields = ["id", "name", "price", "image", "is_available"]


class CartItemSerializer(serializers.ModelSerializer[CartItem]):
    restaurant = PublicIdRelatedField[Restaurant](read_only=True)
    cart_session = PublicIdRelatedField[CartSession](read_only=True)
    menu_item = PublicIdRelatedField[MenuItem](read_only=True)
    menu_item_detail = CartMenuItemSnapshotSerializer(source="menu_item", read_only=True)
    added_by = PublicIdRelatedField[User](read_only=True)
    is_mine = serializers.SerializerMethodField()

    def get_is_mine(self, obj: CartItem) -> bool:
        request = self.context.get("request")
        if request is None:
            return False
        auth = getattr(request, "auth", None)
        payload = getattr(auth, "payload", None)
        if payload is not None and payload.get("is_guest"):
            return obj.guest_identity is not None and obj.guest_identity == payload.get("guest_id")
        user = getattr(request, "user", None)
        return bool(user is not None and not user.is_anonymous and obj.added_by_id == user.id)

    class Meta:
        model = CartItem
        fields = [
            "public_id",
            "menu_item",
            "menu_item_detail",
            "quantity",
            "comment",
            "added_by",
            "guest_slot",
            "is_mine",
            "is_paid",
            "cart_session",
            "restaurant",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "public_id",
            "restaurant",
            "cart_session",
            "menu_item",
            "added_by",
            "guest_slot",
            "is_paid",
            "created_at",
            "updated_at",
        ]


class PayOrderItemsSerializer(serializers.Serializer[None]):
    order_item_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
    )


class BillItemSerializer(serializers.ModelSerializer[OrderItem]):
    id = serializers.UUIDField(source="public_id", read_only=True)
    name = serializers.CharField(source="menu_item.name", read_only=True)
    # Full amount owed for this line (goods + tax + service share). The sum of
    # payable across a visit's items equals Order.total_amount, so the bill the
    # guest pays matches the checkout receipt.
    payable = serializers.DecimalField(max_digits=14, decimal_places=4, read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "name",
            "guest_slot",
            "quantity",
            "total_price",
            "tax_amount",
            "service_charge_amount",
            "payable",
            "is_paid",
        ]


class CheckoutResponseSerializer(serializers.Serializer[None]):
    order_id = serializers.CharField()
    subtotal = serializers.CharField()
    tax = serializers.CharField()
    service_charge = serializers.CharField()
    total = serializers.CharField()
    currency = serializers.CharField()


class UpdateCartItemSerializer(serializers.Serializer[None]):
    quantity = serializers.IntegerField(min_value=1, required=True)
    comment = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    guest_slot = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class AddCartItemSerializer(serializers.Serializer[None]):
    menu_item = PublicIdRelatedField[MenuItem](
        queryset=MenuItem.objects.all(),
        required=True,
    )
    quantity = serializers.IntegerField(min_value=1)
    comment = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    guest_slot = serializers.IntegerField(required=False, allow_null=True, min_value=1)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None:
            restaurant_id = get_restaurant_id_from_auth(request)
            if restaurant_id is not None:
                field = cast(PublicIdRelatedField[MenuItem], self.fields["menu_item"])
                field.queryset = MenuItem.objects.filter(
                    restaurant_id=restaurant_id,
                )
