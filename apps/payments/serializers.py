from rest_framework import serializers

from apps.orders.models import Order
from apps.restaurants.models import Restaurant

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer[Payment]):
    restaurant: serializers.SlugRelatedField[Restaurant] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )
    order: serializers.SlugRelatedField[Order] = serializers.SlugRelatedField(
        slug_field="public_id",
        read_only=True,
    )

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
