from typing import Any

from django import forms
from django.contrib import admin

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

    def prepare_value(self, value: object) -> object:
        if isinstance(value, str):
            import json

            try:
                value = json.loads(value)
            except Exception:  # nosec B110
                pass
        return value


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


class MenuItemInline(admin.TabularInline):  # type: ignore[type-arg]
    model = MenuItem
    fields = ["name", "category", "price", "is_available", "sort_order", "image"]
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
