from django.db.models import Q, QuerySet

from .models import Menu, MenuCategory, MenuItem


def get_active_menus(*, restaurant_id: int) -> QuerySet[Menu]:
    return Menu.objects.filter(restaurant_id=restaurant_id, is_active=True)


def get_categories_by_restaurant(*, restaurant_id: int) -> QuerySet[MenuCategory]:
    return MenuCategory.objects.filter(
        menu__restaurant_id=restaurant_id,
        menu__is_active=True,
    )


def get_menu_items_by_restaurant(*, restaurant_id: int) -> QuerySet[MenuItem]:
    return MenuItem.objects.filter(
        restaurant_id=restaurant_id,
        menu__is_active=True,
    ).select_related("category")


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
