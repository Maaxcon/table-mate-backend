from rest_framework import serializers

from apps.orders.models import Order
from apps.restaurants.models import Restaurant

from .models import Payment, WebhookEvent


class PaymentSerializer(serializers.ModelSerializer[Payment]):
    restaurant: serializers.PrimaryKeyRelatedField[Restaurant] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
    )
    order: serializers.PrimaryKeyRelatedField[Order] = (
        serializers.PrimaryKeyRelatedField(read_only=True)
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


class WebhookEventSerializer(serializers.ModelSerializer[WebhookEvent]):
    class Meta:
        model = WebhookEvent
        fields = [
            "public_id",
            "provider",
            "event_id",
            "payload",
            "received_at",
            "processed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]
