import django_filters
from django.db.models import QuerySet

from .models import MenuCategory, MenuItem


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
            queryset = (
                MenuItem.objects.filter(menu__public_id=menu_uuid)
                .select_related("category")
                .order_by("category__sort_order", "sort_order")
            )
        return super().filter_queryset(queryset)  # type: ignore[no-any-return]
