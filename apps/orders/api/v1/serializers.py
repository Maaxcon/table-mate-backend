from rest_framework import serializers

from apps.authentication.models import User
from apps.menu.models import MenuItem
from apps.orders.models import CartItem, CartSession
from apps.reservations.models import Reservation
from apps.restaurants.models import Restaurant
from common.api import PublicIdRelatedField


class CartSessionSerializer(serializers.ModelSerializer[CartSession]):
    restaurant = PublicIdRelatedField[Restaurant](read_only=True)
    reservation = PublicIdRelatedField[Reservation](
        queryset=Reservation.objects.all(),
        required=True,
    )
    created_by = PublicIdRelatedField[User](read_only=True)
    participants = PublicIdRelatedField[User](many=True, read_only=True)

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
            "participants",
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
            "restaurant",
            "cart_session",
            "menu_item",
            "quantity",
            "added_by",
            "comment",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "public_id",
            "restaurant",
            "cart_session",
            "menu_item",
            "added_by",
            "created_at",
            "updated_at",
        ]


class AddCartItemSerializer(serializers.Serializer[None]):
    menu_item = PublicIdRelatedField[MenuItem](
        queryset=MenuItem.objects.all(),
        required=True,
    )
    quantity = serializers.IntegerField(min_value=1)
    comment = serializers.CharField(required=False, allow_blank=True, default="")
