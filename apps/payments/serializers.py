from rest_framework import serializers

from apps.orders.models import Order
from apps.restaurants.models import Restaurant
from common.api import PublicIdRelatedField

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer[Payment]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    order: PublicIdRelatedField[Order] = PublicIdRelatedField(read_only=True)

    class Meta:
        model = Payment
        fields = [
            "public_id",
            "restaurant",
            "order",
            "provider",
            "provider_transaction_id",
            "amount",
            "currency",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]
