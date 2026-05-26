import django_filters
from django.db.models import QuerySet

from .models import Menu, MenuCategory, MenuItem
from .selectors import get_items_by_category


class MenuCategoryFilter(django_filters.FilterSet):  # type: ignore[misc]
    menu = django_filters.UUIDFilter(field_name="menu__public_id")

    class Meta:
        model = MenuCategory
        fields = ["menu"]


class MenuItemFilter(django_filters.FilterSet):  # type: ignore[misc]
    menu = django_filters.UUIDFilter(field_name="menu__public_id")
    category = django_filters.UUIDFilter(field_name="category__public_id")

    class Meta:
        model = MenuItem
        fields = ["menu", "category", "is_available"]

    def filter_queryset(self, queryset: QuerySet[MenuItem]) -> QuerySet[MenuItem]:
        menu_uuid = self.form.cleaned_data.get("menu")
        if menu_uuid is not None:
            menu = Menu.objects.only("pk").get(public_id=menu_uuid)
            queryset = get_items_by_category(menu_id=menu.pk)
        return super().filter_queryset(queryset)  # type: ignore[no-any-return]
