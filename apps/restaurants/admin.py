from django.contrib import admin

from .models import Restaurant, RestaurantSettings, Table


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ["name", "address", "phone"]


@admin.register(RestaurantSettings)
class RestaurantSettingsAdmin(admin.ModelAdmin):
    list_display = ["restaurant", "currency", "timezone"]


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ["restaurant", "table_number", "capacity", "status"]
