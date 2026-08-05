from datetime import timedelta

from django.db.models import (
    Avg,
    BooleanField,
    Case,
    Count,
    DecimalField,
    Exists,
    IntegerField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Menu, MenuCategory, MenuItem, MenuItemLike

UPSEL_LOOKBACK_DAYS = 90

_DESSERT_DRINK_HINTS = ("dessert", "десерт", "drink", "напій", "напої")


def _dessert_drink_category_ids(*, restaurant_id: int) -> set[int]:
    """Category ids whose name hints at dessert/drink.

    Matching runs in Python because DB case-insensitive operators (UPPER/ILIKE)
    don't fold Cyrillic under a C collation, so SQL ``icontains`` is unreliable
    for Ukrainian category names.
    """
    names = (
        MenuCategory.objects.filter(menu__restaurant_id=restaurant_id, menu__is_active=True)
        .values_list("id", "name")
        .all()
    )
    return {category_id for category_id, name in names if any(hint in name.lower() for hint in _DESSERT_DRINK_HINTS)}


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


def _order_item_popularity_subquery(restaurant_id: int) -> Subquery:
    """Count of non-voided order-items per menu item, used as a popularity tiebreak."""
    from apps.orders.models import OrderItem, OrderStatus

    lookback = timezone.now() - timedelta(days=UPSEL_LOOKBACK_DAYS)
    return Subquery(
        OrderItem.objects.filter(
            menu_item_id=OuterRef("pk"),
            restaurant_id=restaurant_id,
            voided_at__isnull=True,
            order__status=OrderStatus.COMPLETED,
            order__created_at__gte=lookback,
        )
        .values("menu_item_id")
        .annotate(total=Count("id"))
        .values("total"),
        output_field=IntegerField(),
    )


def get_upsell_suggestions(
    *,
    restaurant_id: int,
    target_item: MenuItem,
    guest_token: str | None = None,
    limit: int = 6,
) -> QuerySet[MenuItem]:
    """Rank available items by how often they were ordered together with the target.

    Co-occurrence is derived at query time from completed, non-voided order history
    within the lookback window (per the constitution's query-time metric rule). The
    target itself, unavailable items, and items from other restaurants are excluded.
    """
    from apps.orders.models import OrderItem, OrderStatus

    lookback = timezone.now() - timedelta(days=UPSEL_LOOKBACK_DAYS)
    target_order_ids = (
        OrderItem.objects.filter(
            order__restaurant_id=restaurant_id,
            order__status=OrderStatus.COMPLETED,
            order__created_at__gte=lookback,
            menu_item=target_item,
            voided_at__isnull=True,
        )
        .values_list("order_id", flat=True)
        .distinct()
    )
    qs = (
        MenuItem.objects.filter(
            restaurant_id=restaurant_id,
            is_available=True,
            menu__is_active=True,
        )
        .exclude(pk=target_item.pk)
        .select_related("category")
        .annotate(
            cooccurrence_count=Count(
                "order_items__order_id",
                distinct=True,
                filter=Q(
                    order_items__order_id__in=target_order_ids,
                    order_items__voided_at__isnull=True,
                ),
            ),
            popularity=Coalesce(_order_item_popularity_subquery(restaurant_id), 0),
        )
        .filter(cooccurrence_count__gt=0)
        .order_by("-cooccurrence_count", "-popularity", "menu_id", "sort_order", "id")
    )
    return _with_like_annotations(qs, guest_token=guest_token)[:limit]


def get_default_upsell_items(
    *,
    restaurant_id: int,
    target_item: MenuItem,
    guest_token: str | None = None,
    limit: int = 6,
    exclude_ids: set[int] | None = None,
) -> QuerySet[MenuItem]:
    """Fallback suggestions for restaurants with sparse order history.

    Prefers dessert/drink-named categories, then the most popular available items,
    so an available dish never yields an empty suggestion set.
    """
    qs = (
        MenuItem.objects.filter(
            restaurant_id=restaurant_id,
            is_available=True,
            menu__is_active=True,
        )
        .exclude(pk=target_item.pk)
        .select_related("category")
    )
    if exclude_ids:
        qs = qs.exclude(pk__in=exclude_ids)
    dessert_drink_ids = _dessert_drink_category_ids(restaurant_id=restaurant_id)
    qs = qs.annotate(
        is_dessert_drink=Case(
            When(category_id__in=dessert_drink_ids, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        ),
        popularity=Coalesce(_order_item_popularity_subquery(restaurant_id), 0),
    ).order_by("-is_dessert_drink", "-popularity", "menu_id", "sort_order", "id")
    return _with_like_annotations(qs, guest_token=guest_token)[:limit]
