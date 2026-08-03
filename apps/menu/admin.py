from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from .models import (
    Allergen,
    AllergenTranslation,
    Ingredient,
    IngredientTranslation,
    Menu,
    MenuCategory,
    MenuCategoryTranslation,
    MenuItem,
    MenuItemAllergen,
    MenuItemIngredient,
    MenuItemTranslation,
    MenuTranslation,
)


class MenuCategoryInline(admin.TabularInline):  # type: ignore[type-arg]
    model = MenuCategory
    extra = 0


class MenuTranslationInline(admin.TabularInline):  # type: ignore[type-arg]
    model = MenuTranslation
    extra = 0


class MenuCategoryTranslationInline(admin.TabularInline):  # type: ignore[type-arg]
    model = MenuCategoryTranslation
    extra = 0


class MenuItemTranslationInline(admin.TabularInline):  # type: ignore[type-arg]
    model = MenuItemTranslation
    extra = 0


class MenuItemAllergenInline(admin.TabularInline):  # type: ignore[type-arg]
    model = MenuItemAllergen
    extra = 0
    autocomplete_fields = ["allergen"]


class MenuItemIngredientInline(admin.TabularInline):  # type: ignore[type-arg]
    model = MenuItemIngredient
    extra = 0
    autocomplete_fields = ["ingredient"]


class AllergenTranslationInline(admin.TabularInline):  # type: ignore[type-arg]
    model = AllergenTranslation
    extra = 0


class IngredientTranslationInline(admin.TabularInline):  # type: ignore[type-arg]
    model = IngredientTranslation
    extra = 0


@admin.register(Allergen)
class AllergenAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["name", "restaurant", "sort_order"]
    list_filter = ["restaurant"]
    search_fields = ["name"]
    inlines = [AllergenTranslationInline]


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["name", "restaurant", "sort_order"]
    list_filter = ["restaurant"]
    search_fields = ["name"]
    inlines = [IngredientTranslationInline]


@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["name", "restaurant", "is_active"]
    inlines = [MenuCategoryInline, MenuTranslationInline]


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["name", "menu", "sort_order", "color"]
    inlines = [MenuCategoryTranslationInline]


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["name", "restaurant", "category", "price", "is_available"]
    list_filter = ["restaurant", "category", "is_available"]
    search_fields = ["name"]
    inlines = [
        MenuItemTranslationInline,
        MenuItemAllergenInline,
        MenuItemIngredientInline,
    ]

    def get_form(self, request: HttpRequest, obj: MenuItem | None = None, change: bool = False, **kwargs: Any) -> Any:
        request._menuitem_menu_id = obj.menu_id if obj else None  # type: ignore[attr-defined]
        return super().get_form(request, obj, change=change, **kwargs)

    def formfield_for_foreignkey(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:
        if db_field.name == "category":
            menu_id = getattr(request, "_menuitem_menu_id", None)
            qs = MenuCategory.objects.all()
            kwargs["queryset"] = qs.filter(menu_id=menu_id) if menu_id else qs
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
