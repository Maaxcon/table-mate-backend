from django.contrib import admin

from .models import Menu, MenuCategory, MenuItem


class MenuCategoryInline(admin.TabularInline):
    model = MenuCategory
    extra = 0


class MenuItemInline(admin.TabularInline):
    model = MenuItem
    fields = ["name", "category", "price", "is_available", "sort_order", "image"]
    extra = 0


@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    list_display = ["name", "restaurant", "is_active"]
    inlines = [MenuCategoryInline]


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "menu", "sort_order"]


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ["name", "restaurant", "category", "price", "is_available"]
    list_filter = ["restaurant", "category", "is_available"]
    search_fields = ["name"]
