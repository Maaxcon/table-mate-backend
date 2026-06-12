from typing import Any

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.menu.models import MenuItem

from .models import Receipt, ReceiptItem


class ReceiptItemInline(admin.TabularInline):  # type: ignore[type-arg]
    model = ReceiptItem
    extra = 1
    fields = ["menu_item", "name", "quantity", "unit_price", "line_total"]
    readonly_fields = ["line_total"]

    @admin.display(description="Line total")
    def line_total(self, obj: ReceiptItem) -> str:
        return f"{obj.line_total:.2f}"

    def get_formset(self, request: HttpRequest, obj: Receipt | None = None, **kwargs: Any) -> Any:
        # Remember which restaurant this receipt belongs to (change page only) so
        # the dish dropdown can be limited to that restaurant's menu. Stored on the
        # request, not self: admin instances are shared across threads/requests.
        request._receipt_restaurant_id = obj.restaurant_id if obj else None  # type: ignore[attr-defined]
        return super().get_formset(request, obj, **kwargs)

    def formfield_for_foreignkey(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:
        if db_field.name == "menu_item":
            restaurant_id = getattr(request, "_receipt_restaurant_id", None)
            qs = MenuItem.objects.all()
            kwargs["queryset"] = qs.filter(restaurant_id=restaurant_id) if restaurant_id else qs.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


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

    def get_queryset(self, request: HttpRequest) -> QuerySet[Receipt]:
        # Prefetch items (used by subtotal/total) and related FKs to avoid N+1
        # queries when rendering the list and computed columns.
        return super().get_queryset(request).select_related("customer", "restaurant").prefetch_related("items")

    @admin.display(description="Subtotal")
    def subtotal_display(self, obj: Receipt) -> str:
        return f"{obj.subtotal:.2f} {obj.currency}"

    @admin.display(description="Total")
    def total_display(self, obj: Receipt) -> str:
        return f"{obj.total:.2f} {obj.currency}"
