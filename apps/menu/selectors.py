from django.db.models import BooleanField, Count, Exists, OuterRef, Q, QuerySet, Value

from .models import Menu, MenuCategory, MenuItem, MenuItemLike


def get_active_menus(*, restaurant_id: int) -> QuerySet[Menu]:
    return Menu.objects.filter(restaurant_id=restaurant_id, is_active=True)


def get_categories_by_restaurant(*, restaurant_id: int) -> QuerySet[MenuCategory]:
    return MenuCategory.objects.filter(
        menu__restaurant_id=restaurant_id,
        menu__is_active=True,
    )


def _with_like_annotations(qs: QuerySet[MenuItem], *, guest_token: str | None) -> QuerySet[MenuItem]:
    qs = qs.annotate(likes_count=Count("likes", distinct=True))
    if guest_token:
        return qs.annotate(
            is_liked=Exists(
                MenuItemLike.objects.filter(
                    menu_item_id=OuterRef("pk"),
                    guest_token=guest_token,
                )
            )
        )
    return qs.annotate(is_liked=Value(False, output_field=BooleanField()))


def get_menu_items_by_restaurant(*, restaurant_id: int, guest_token: str | None = None) -> QuerySet[MenuItem]:
    qs = MenuItem.objects.filter(
        restaurant_id=restaurant_id,
        menu__is_active=True,
    ).select_related("category")
    return _with_like_annotations(qs, guest_token=guest_token)


def search_menu_items(
    *,
    query: str,
    restaurant_id: int,
    guest_token: str | None = None,
) -> QuerySet[MenuItem]:
    qs = MenuItem.objects.filter(
        restaurant_id=restaurant_id,
        is_available=True,
    ).filter(
        Q(name__icontains=query) | Q(description__icontains=query),
    ).select_related("category")
    return _with_like_annotations(qs, guest_token=guest_token)
