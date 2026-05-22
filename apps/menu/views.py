from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from common.api import PublicLookupMixin, PublicRestaurantQueryMixin

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
    filterset_fields = ["menu"]
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
    filterset_fields = ["menu", "category", "is_available"]
    ordering_fields = ["created_at", "updated_at", "sort_order", "name", "price"]

    def get_queryset(self) -> QuerySet[MenuItem]:
        restaurant_id = self.get_restaurant_id()
        if restaurant_id is None:
            return MenuItem.objects.none()
        return get_menu_items_by_restaurant(restaurant_id=restaurant_id)

    @action(detail=False, methods=["get"])
    def search(self, request: Request) -> Response:
        query = request.query_params.get("q", "")
        restaurant_id = self.get_restaurant_id()
        if restaurant_id is None or not query:
            return Response([])
        items = search_menu_items(query=query, restaurant_id=restaurant_id)
        serializer = self.get_serializer(items, many=True)
        return Response(serializer.data)
