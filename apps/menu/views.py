from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from common.api import RestaurantScopedViewSetMixin

from .models import Menu, MenuCategory, MenuItem
from .serializers import MenuCategorySerializer, MenuItemSerializer, MenuSerializer


@extend_schema(tags=["Menu"])
class MenuViewSet(
    RestaurantScopedViewSetMixin[Menu],
    viewsets.ReadOnlyModelViewSet[Menu],
):
    queryset = Menu.objects.all()
    serializer_class = MenuSerializer
    filterset_fields = ["is_active"]
    ordering_fields = ["created_at", "updated_at", "name"]


@extend_schema(tags=["Menu"])
class MenuCategoryViewSet(
    RestaurantScopedViewSetMixin[MenuCategory],
    viewsets.ReadOnlyModelViewSet[MenuCategory],
):
    queryset = MenuCategory.objects.all()
    serializer_class = MenuCategorySerializer
    restaurant_lookup = "menu__restaurant_id"
    filterset_fields = ["menu"]
    ordering_fields = ["created_at", "updated_at", "sort_order", "name"]


@extend_schema(tags=["Menu"])
class MenuItemViewSet(
    RestaurantScopedViewSetMixin[MenuItem],
    viewsets.ReadOnlyModelViewSet[MenuItem],
):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
    filterset_fields = ["menu", "category", "is_available"]
    ordering_fields = ["created_at", "updated_at", "sort_order", "name", "price"]
