from django.contrib import admin

from .models import Restaurant, RestaurantSettings, Table


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["name", "address", "phone", "telegram_url", "facebook_url"]
    search_fields = ["name", "address"]


@admin.register(RestaurantSettings)
class RestaurantSettingsAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["restaurant", "currency", "timezone"]


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["restaurant", "table_number", "capacity"]
