from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from common.api import PublicLookupMixin, PublicRestaurantQueryMixin

from .filters import MenuCategoryFilter, MenuItemFilter
from .models import Menu, MenuCategory, MenuItem
from .selectors import (
    get_active_menus,
    get_categories_by_restaurant,
    get_menu_items_by_restaurant,
    search_menu_items,
)
from .serializers import MenuCategorySerializer, MenuItemSerializer, MenuSerializer


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
        restaurant_id = self.get_restaurant_id()
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
        restaurant_id = self.get_restaurant_id()
        if restaurant_id is None:
            return MenuCategory.objects.none()
        return get_categories_by_restaurant(restaurant_id=restaurant_id)


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
        restaurant_id = self.get_restaurant_id()
        if restaurant_id is None:
            return MenuItem.objects.none()
        return get_menu_items_by_restaurant(restaurant_id=restaurant_id)

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
        ],
    )
    def search(self, request: Request) -> Response:
        query = request.query_params.get("q", "").strip()
        restaurant_id = self.get_restaurant_id()
        if not query or restaurant_id is None:
            return self.get_paginated_response([]) if self.paginator else Response([])
        items = search_menu_items(query=query, restaurant_id=restaurant_id)
        page = self.paginate_queryset(items)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(items, many=True).data)
