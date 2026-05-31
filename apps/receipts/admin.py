from django.contrib import admin

from .models import Receipt, ReceiptItem


class ReceiptItemInline(admin.TabularInline):  # type: ignore[type-arg]
    model = ReceiptItem
    extra = 1
    fields = ["name", "quantity", "unit_price", "line_total"]
    readonly_fields = ["line_total"]

    @admin.display(description="Line total")
    def line_total(self, obj: ReceiptItem) -> str:
        return f"{obj.line_total:.2f}"


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    inlines = [ReceiptItemInline]
    list_display = [
        "order_number",
        "customer",
        "restaurant",
        "visited_at",
        "total_display",
        "payment_method",
        "payment_status",
    ]
    list_filter = ["restaurant", "payment_method", "payment_status", "visited_at"]
    search_fields = ["order_number", "customer__email", "server_name"]
    autocomplete_fields = ["customer", "restaurant"]
    date_hierarchy = "visited_at"
    readonly_fields = ["subtotal_display", "total_display"]
    fieldsets = [
        (
            "Who & where",
            {"fields": ["customer", "restaurant", "order_number", "visited_at"]},
        ),
        (
            "Visit",
            {"fields": ["table_label", "server_name", "guests", "currency"]},
        ),
        (
            "Charges",
            {
                "fields": [
                    "tax",
                    "service_charge",
                    "tip",
                    "subtotal_display",
                    "total_display",
                ]
            },
        ),
        (
            "Payment",
            {"fields": ["payment_method", "payment_status"]},
        ),
    ]

    @admin.display(description="Subtotal")
    def subtotal_display(self, obj: Receipt) -> str:
        return f"{obj.subtotal:.2f} {obj.currency}"

    @admin.display(description="Total")
    def total_display(self, obj: Receipt) -> str:
        return f"{obj.total:.2f} {obj.currency}"
