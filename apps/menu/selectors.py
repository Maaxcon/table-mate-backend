from django.db.models import Q, QuerySet

from .models import Menu, MenuItem


def get_active_menus(*, restaurant_id: int) -> QuerySet[Menu]:
    return Menu.objects.filter(restaurant_id=restaurant_id, is_active=True)


def get_items_by_category(*, menu_id: int) -> QuerySet[MenuItem]:
    return (
        MenuItem.objects.filter(menu_id=menu_id)
        .select_related("category")
        .order_by("category__sort_order", "sort_order")
    )


def search_menu_items(*, query: str, restaurant_id: int) -> QuerySet[MenuItem]:
    return MenuItem.objects.filter(
        restaurant_id=restaurant_id,
        is_available=True,
    ).filter(
        Q(name__icontains=query) | Q(description__icontains=query),
    )
