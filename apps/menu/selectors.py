from django.db.models import (
    Avg,
    BooleanField,
    Count,
    DecimalField,
    Exists,
    OuterRef,
    Q,
    QuerySet,
    Value,
)
from django.db.models.functions import Coalesce

from .models import Menu, MenuCategory, MenuItem, MenuItemLike


def get_active_menus(*, restaurant_id: int) -> QuerySet[Menu]:
    return Menu.objects.filter(restaurant_id=restaurant_id, is_active=True).prefetch_related("items", "categories")


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


def _with_rating_annotations(qs: QuerySet[MenuItem]) -> QuerySet[MenuItem]:
    return qs.annotate(
        average_rating=Coalesce(
            Avg("dish_feedback__rating"),
            None,
            output_field=DecimalField(max_digits=3, decimal_places=2),
        ),
        rating_count=Count("dish_feedback", distinct=True),
    )


def get_menu_items_by_restaurant(*, restaurant_id: int, guest_token: str | None = None) -> QuerySet[MenuItem]:
    qs = MenuItem.objects.filter(
        restaurant_id=restaurant_id,
        menu__is_active=True,
    ).select_related("category")
    qs = _with_rating_annotations(qs)
    # Explicit order: the likes_count aggregate adds a GROUP BY, which makes
    # Django drop Meta.ordering and warn under pagination.
    return _with_like_annotations(qs, guest_token=guest_token).order_by("menu_id", "sort_order", "id")


def search_menu_items(
    *,
    query: str,
    restaurant_id: int,
    guest_token: str | None = None,
) -> QuerySet[MenuItem]:
    qs = (
        MenuItem.objects.filter(
            restaurant_id=restaurant_id,
            is_available=True,
        )
        .filter(
            Q(name__icontains=query) | Q(description__icontains=query) | Q(category__name__icontains=query),
        )
        .select_related("category")
    )
    qs = _with_rating_annotations(qs)
    return _with_like_annotations(qs, guest_token=guest_token).order_by("menu_id", "sort_order", "id")
