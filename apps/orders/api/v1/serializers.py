from typing import Any, cast

from rest_framework import serializers

from apps.authentication.models import User
from apps.menu.models import MenuItem
from apps.orders.models import CartItem, CartSession
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


class CartItemSerializer(serializers.ModelSerializer[CartItem]):
    restaurant = PublicIdRelatedField[Restaurant](read_only=True)
    cart_session = PublicIdRelatedField[CartSession](read_only=True)
    menu_item = PublicIdRelatedField[MenuItem](read_only=True)
    added_by = PublicIdRelatedField[User](read_only=True)

    class Meta:
        model = CartItem
        fields = [
            "public_id",
            "menu_item",
            "quantity",
            "comment",
            "added_by",
            "guest_slot",
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
