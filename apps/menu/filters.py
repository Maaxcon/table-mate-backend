import django_filters

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
