from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from common.api import PublicLookupMixin

from .models import Menu, MenuCategory, MenuItem
from .serializers import MenuCategorySerializer, MenuItemSerializer, MenuSerializer


@extend_schema(tags=["Menu"])
class MenuViewSet(
    PublicLookupMixin,
    viewsets.ReadOnlyModelViewSet[Menu],
):
    queryset = Menu.objects.all()
    serializer_class = MenuSerializer
    permission_classes = [AllowAny]
    filterset_fields = ["is_active"]
    ordering_fields = ["created_at", "updated_at", "name"]


@extend_schema(tags=["Menu"])
class MenuCategoryViewSet(
    PublicLookupMixin,
    viewsets.ReadOnlyModelViewSet[MenuCategory],
):
    queryset = MenuCategory.objects.all()
    serializer_class = MenuCategorySerializer
    permission_classes = [AllowAny]
    filterset_fields = ["menu"]
    ordering_fields = ["created_at", "updated_at", "sort_order", "name"]


@extend_schema(tags=["Menu"])
class MenuItemViewSet(
    PublicLookupMixin,
    viewsets.ReadOnlyModelViewSet[MenuItem],
):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
    permission_classes = [AllowAny]
    filterset_fields = ["menu", "category", "is_available"]
    ordering_fields = ["created_at", "updated_at", "sort_order", "name", "price"]
