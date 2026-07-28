import django_filters
from django.db.models import QuerySet

from .models import Allergen, MenuCategory, MenuItem


def allergen_choices() -> list[tuple[str, str]]:
    return list(Allergen.objects.values_list("name", "name"))


class MenuCategoryFilter(django_filters.FilterSet):  # type: ignore[misc]
    menu = django_filters.UUIDFilter(field_name="menu__public_id")

    class Meta:
        model = MenuCategory
        fields = ["menu"]


class MenuItemFilter(django_filters.FilterSet):  # type: ignore[misc]
    menu = django_filters.UUIDFilter(field_name="menu__public_id")
    category = django_filters.UUIDFilter(field_name="category__public_id")
    allergens = django_filters.MultipleChoiceFilter(
        choices=allergen_choices,
        method="filter_allergens",
    )
    ingredients = django_filters.CharFilter(method="filter_ingredients")

    class Meta:
        model = MenuItem
        fields = ["menu", "category", "is_available"]

    def filter_queryset(self, queryset: QuerySet[MenuItem]) -> QuerySet[MenuItem]:
        menu_uuid = self.form.cleaned_data.get("menu")
        if menu_uuid is not None:
            queryset = (
                queryset.filter(menu__public_id=menu_uuid)
                .select_related("category")
                .order_by("category__sort_order", "sort_order")
            )
        return super().filter_queryset(queryset)  # type: ignore[no-any-return]

    def filter_allergens(
        self,
        queryset: QuerySet[MenuItem],
        name: str,
        values: list[str],
    ) -> QuerySet[MenuItem]:
        for allergen in values:
            queryset = queryset.exclude(allergens__contains=[allergen])
        return queryset

    def filter_ingredients(self, queryset: QuerySet[MenuItem], name: str, value: str) -> QuerySet[MenuItem]:
        return queryset.filter(ingredients__contains=[value])
