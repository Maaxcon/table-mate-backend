from typing import Any

from django import forms
from django.contrib import admin
from django.http import HttpRequest

from .allergens import ALLERGENS
from .models import Menu, MenuCategory, MenuItem


class AllergenCheckboxWidget(forms.CheckboxSelectMultiple):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("choices", [(a, a) for a in ALLERGENS])
        super().__init__(*args, **kwargs)


class AllergenField(forms.MultipleChoiceField):
    widget = AllergenCheckboxWidget

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("choices", [(a, a) for a in ALLERGENS])
        kwargs.setdefault("required", False)
        super().__init__(*args, **kwargs)


class MenuItemForm(forms.ModelForm):  # type: ignore[type-arg]
    allergens = AllergenField()

    class Meta:
        model = MenuItem
        fields = "__all__"

    def clean_allergens(self) -> list[str]:
        return self.cleaned_data.get("allergens") or []


class MenuCategoryInline(admin.TabularInline):  # type: ignore[type-arg]
    model = MenuCategory
    extra = 0


@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["name", "restaurant", "is_active"]
    inlines = [MenuCategoryInline]


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["name", "menu", "sort_order"]


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    form = MenuItemForm
    list_display = ["name", "restaurant", "category", "price", "is_available"]
    list_filter = ["restaurant", "category", "is_available"]
    search_fields = ["name"]

    def get_form(
        self, request: HttpRequest, obj: MenuItem | None = None, change: bool = False, **kwargs: Any
    ) -> Any:
        # Stored on the request, not self: admin instances are shared across
        # threads/requests, so self-state can leak between concurrent edits.
        request._menuitem_menu_id = obj.menu_id if obj else None  # type: ignore[attr-defined]
        return super().get_form(request, obj, change=change, **kwargs)

    def formfield_for_foreignkey(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:
        if db_field.name == "category":
            menu_id = getattr(request, "_menuitem_menu_id", None)
            qs = MenuCategory.objects.all()
            kwargs["queryset"] = qs.filter(menu_id=menu_id) if menu_id else qs
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
