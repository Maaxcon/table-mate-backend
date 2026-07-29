from rest_framework import serializers

from .models import Receipt, ReceiptItem


class ReceiptItemSerializer(serializers.ModelSerializer[ReceiptItem]):
    menu_item_public_id = serializers.UUIDField(source="menu_item.public_id", read_only=True, allow_null=True)

    class Meta:
        model = ReceiptItem
        fields = ["menu_item_public_id", "name", "quantity", "unit_price"]


class ReceiptSerializer(serializers.ModelSerializer[Receipt]):
    items = ReceiptItemSerializer(many=True, read_only=True)
    order_public_id = serializers.UUIDField(source="order.public_id", read_only=True, allow_null=True)
    restaurant_public_id = serializers.CharField(source="restaurant.public_id", read_only=True)
    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)
    restaurant_address = serializers.CharField(source="restaurant.address", read_only=True)
    restaurant_phone = serializers.CharField(source="restaurant.phone", read_only=True)
    restaurant_image = serializers.SerializerMethodField()
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Receipt
        fields = [
            "public_id",
            "order_public_id",
            "order_number",
            "restaurant_public_id",
            "restaurant_name",
            "restaurant_address",
            "restaurant_phone",
            "restaurant_image",
            "visited_at",
            "currency",
            "table_label",
            "server_name",
            "guests",
            "items",
            "subtotal",
            "tax",
            "service_charge",
            "tip",
            "total",
            "payment_method",
            "payment_status",
        ]

    def get_restaurant_image(self, obj: Receipt) -> str | None:
        image = getattr(obj.restaurant, "cover_image", None)
        if not image:
            return None
        request = self.context.get("request")
        url: str = image.url
        return str(request.build_absolute_uri(url)) if request else url
