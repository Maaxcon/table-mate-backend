from typing import Any

from django.db import transaction
from django.db.models import Count, QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView

from apps.authentication.permissions import IsAdmin
from common.api import (
    PublicLookupMixin,
    PublicRestaurantQueryMixin,
    RestaurantScopedViewSetMixin,
    get_restaurant_id_from_auth,
)

from . import services
from .allergens import ALLERGENS
from .filters import MenuCategoryFilter, MenuItemFilter
from .models import Menu, MenuCategory, MenuItem, MenuItemLike
from .selectors import (
    get_active_menus,
    get_categories_by_restaurant,
    get_menu_items_by_restaurant,
    search_menu_items,
)
from .serializers import (
    AdminMenuCategorySerializer,
    AdminMenuItemSerializer,
    AdminMenuSerializer,
    BulkItemActionSerializer,
    MenuCategorySerializer,
    MenuItemSerializer,
    MenuSerializer,
    ReorderEntrySerializer,
    ToggleMenuItemLikeRequestSerializer,
    ToggleMenuItemLikeResponseSerializer,
)


def _reorder_view(viewset: Any, request: Request) -> Response:
    """Validate {public_id, sort_order} entries and delegate to the reorder service."""
    serializer = ReorderEntrySerializer(data=request.data, many=True)
    serializer.is_valid(raise_exception=True)
    services.reorder(viewset.get_queryset(), serializer.validated_data)
    return Response(status=status.HTTP_204_NO_CONTENT)


def _get_serializer_fields(serializer: BaseSerializer[Any]) -> Any:
    target = getattr(serializer, "child", serializer)
    return getattr(target, "fields", {})


@extend_schema(tags=["Menu"])
class MenuViewSet(
    PublicRestaurantQueryMixin,
    PublicLookupMixin,
    viewsets.ReadOnlyModelViewSet[Menu],
):
    serializer_class = MenuSerializer
    permission_classes = [AllowAny]
    ordering_fields = ["created_at", "updated_at", "name"]

    def get_queryset(self) -> QuerySet[Menu]:
        restaurant_id = self.resolve_restaurant_or_not_found()
        if restaurant_id is None:
            return Menu.objects.none()
        return get_active_menus(restaurant_id=restaurant_id)


@extend_schema(tags=["Menu"])
class MenuCategoryViewSet(
    PublicRestaurantQueryMixin,
    PublicLookupMixin,
    viewsets.ReadOnlyModelViewSet[MenuCategory],
):
    serializer_class = MenuCategorySerializer
    permission_classes = [AllowAny]
    filterset_class = MenuCategoryFilter
    ordering_fields = ["created_at", "updated_at", "sort_order", "name"]

    def get_queryset(self) -> QuerySet[MenuCategory]:
        restaurant_id = self.resolve_restaurant_or_not_found()
        if restaurant_id is None:
            return MenuCategory.objects.none()
        return get_categories_by_restaurant(restaurant_id=restaurant_id)


@extend_schema(tags=["Menu Admin"])
class AdminMenuViewSet(
    RestaurantScopedViewSetMixin[Menu],
    viewsets.ModelViewSet[Menu],
):
    permission_classes = [IsAdmin]
    queryset = Menu.objects.all()
    serializer_class = AdminMenuSerializer
    restaurant_lookup = "restaurant_id"
    ordering_fields = ["name", "created_at", "updated_at"]

    def perform_create(self, serializer: BaseSerializer[Menu]) -> None:
        # Menu belongs to the admin's restaurant, taken from the auth context.
        serializer.save(restaurant_id=get_restaurant_id_from_auth(self.request))


@extend_schema(tags=["Menu Admin"])
class AdminMenuCategoryViewSet(
    RestaurantScopedViewSetMixin[MenuCategory],
    viewsets.ModelViewSet[MenuCategory],
):
    permission_classes = [IsAdmin]
    queryset = MenuCategory.objects.all()
    serializer_class = AdminMenuCategorySerializer
    restaurant_lookup = "menu__restaurant_id"
    filterset_class = MenuCategoryFilter
    ordering_fields = ["sort_order", "name", "created_at", "updated_at"]

    def get_serializer(self, *args: object, **kwargs: object) -> BaseSerializer[MenuCategory]:
        serializer = super().get_serializer(*args, **kwargs)
        # Restrict the selectable menu to the admin's own restaurant, so an admin
        # cannot attach a category to another restaurant's menu.
        restaurant_id = get_restaurant_id_from_auth(self.request)
        fields = _get_serializer_fields(serializer)
        if "menu" in fields:
            fields["menu"].queryset = (
                Menu.objects.filter(restaurant_id=restaurant_id) if restaurant_id is not None else Menu.objects.none()
            )
        return serializer

    @extend_schema(request=ReorderEntrySerializer(many=True), responses={204: None})
    @action(detail=False, methods=["post"])
    def reorder(self, request: Request) -> Response:
        return _reorder_view(self, request)


@extend_schema(tags=["Menu Admin"])
class AdminMenuItemViewSet(
    RestaurantScopedViewSetMixin[MenuItem],
    viewsets.ModelViewSet[MenuItem],
):
    permission_classes = [IsAdmin]
    queryset = MenuItem.objects.all()
    serializer_class = AdminMenuItemSerializer
    restaurant_lookup = "restaurant_id"
    filterset_class = MenuItemFilter
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    ordering_fields = ["sort_order", "name", "price", "created_at", "updated_at"]

    def safely_get_queryset(self, qs: QuerySet[MenuItem]) -> QuerySet[MenuItem]:
        # Expose a likes_count for the admin (used by the dashboard charts). The
        # aggregate adds a GROUP BY, so set an explicit order to keep pagination
        # stable (Django otherwise drops Meta.ordering and warns).
        return qs.annotate(likes_count=Count("likes", distinct=True)).order_by(
            "menu_id", "sort_order", "id"
        )

    def get_serializer(self, *args: object, **kwargs: object) -> BaseSerializer[MenuItem]:
        serializer = super().get_serializer(*args, **kwargs)
        restaurant_id = get_restaurant_id_from_auth(self.request)
        fields = _get_serializer_fields(serializer)
        if "menu" in fields:
            fields["menu"].queryset = (
                Menu.objects.filter(restaurant_id=restaurant_id) if restaurant_id is not None else Menu.objects.none()
            )
        if "category" in fields:
            fields["category"].queryset = (
                MenuCategory.objects.filter(menu__restaurant_id=restaurant_id)
                if restaurant_id is not None
                else MenuCategory.objects.none()
            )
        return serializer

    def perform_create(self, serializer: BaseSerializer[MenuItem]) -> None:
        serializer.save(restaurant_id=get_restaurant_id_from_auth(self.request))

    @extend_schema(request=ReorderEntrySerializer(many=True), responses={204: None})
    @action(detail=False, methods=["post"])
    def reorder(self, request: Request) -> Response:
        return _reorder_view(self, request)

    @extend_schema(request=BulkItemActionSerializer, responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["post"])
    def bulk(self, request: Request) -> Response:
        """Hide/show, set the category of, or delete several dishes at once."""
        serializer = BulkItemActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.bulk_update_items(
            restaurant_id=get_restaurant_id_from_auth(request),
            data=serializer.validated_data,
        )
        return Response(result, status=status.HTTP_200_OK)

    @extend_schema(request=None, responses={201: AdminMenuItemSerializer})
    @action(detail=True, methods=["post"])
    def duplicate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        copy = services.duplicate_item(self.get_object())
        return Response(self.get_serializer(copy).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Menu"])
class MenuItemViewSet(
    PublicRestaurantQueryMixin,
    PublicLookupMixin,
    viewsets.ReadOnlyModelViewSet[MenuItem],
):
    serializer_class = MenuItemSerializer
    permission_classes = [AllowAny]
    filterset_class = MenuItemFilter
    ordering_fields = ["created_at", "updated_at", "sort_order", "name", "price"]

    def get_queryset(self) -> QuerySet[MenuItem]:
        restaurant_id = self.resolve_restaurant_or_not_found()
        if restaurant_id is None:
            return MenuItem.objects.none()
        guest_token = self.request.query_params.get("guest_token")
        return get_menu_items_by_restaurant(restaurant_id=restaurant_id, guest_token=guest_token)

    @action(detail=False, methods=["get"])
    @extend_schema(
        summary="Full-text search across menu items",
        parameters=[
            OpenApiParameter(name="q", description="Search query", required=True, type=str),
            OpenApiParameter(
                name="restaurant",
                description="Restaurant public UUID",
                required=True,
                type=str,
            ),
            OpenApiParameter(
                name="guest_token",
                description="Anonymous client token for personalized like state.",
                required=False,
                type=str,
            ),
        ],
    )
    def search(self, request: Request) -> Response:
        query = request.query_params.get("q", "").strip()
        restaurant_id = self.resolve_restaurant_or_not_found()
        if not query or restaurant_id is None:
            page = self.paginate_queryset(MenuItem.objects.none())
            if page is not None:
                return self.get_paginated_response([])
            return Response([])
        guest_token = request.query_params.get("guest_token")
        items = search_menu_items(
            query=query,
            restaurant_id=restaurant_id,
            guest_token=guest_token,
        )
        page = self.paginate_queryset(items)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(items, many=True).data)

    @extend_schema(
        summary="Toggle like on a menu item for an anonymous client token",
        request=ToggleMenuItemLikeRequestSerializer,
        responses={status.HTTP_200_OK: ToggleMenuItemLikeResponseSerializer},
        parameters=[
            OpenApiParameter(
                name="restaurant",
                description="Restaurant public UUID",
                required=True,
                type=OpenApiTypes.UUID,
            ),
        ],
    )
    @action(detail=True, methods=["post"], url_path="toggle-like")
    def toggle_like(self, request: Request, *args: object, **kwargs: object) -> Response:
        serializer = ToggleMenuItemLikeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        guest_token = str(serializer.validated_data["guest_token"])

        item = self.get_object()
        with transaction.atomic():
            # Lock the MenuItem row to serialize concurrent toggles for the same item.
            # Without this, two simultaneous requests can both find no like, both INSERT,
            # causing IntegrityError → get_or_create retry finds the row → deletes it,
            # leaving the item unliked even though both requests intended to like it.
            locked_item = MenuItem.objects.select_for_update().get(pk=item.pk)

            existing = MenuItemLike.objects.filter(
                menu_item=locked_item,
                guest_token=guest_token,
            ).first()

            if existing:
                existing.delete()
                is_liked = False
            else:
                MenuItemLike.objects.create(
                    menu_item=locked_item,
                    guest_token=guest_token,
                    restaurant=locked_item.restaurant,
                )
                is_liked = True

            likes_count = MenuItemLike.objects.filter(menu_item=locked_item).count()
        response_serializer = ToggleMenuItemLikeResponseSerializer(
            data={
                "public_id": item.public_id,
                "is_liked": is_liked,
                "likes_count": likes_count,
            }
        )
        response_serializer.is_valid(raise_exception=True)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Menu"],
    responses={200: serializers.ListSerializer(child=serializers.CharField())},
)
class AllergenListView(APIView):
    """The allowed allergen vocabulary — the single source of truth for clients."""

    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        return Response(ALLERGENS)
