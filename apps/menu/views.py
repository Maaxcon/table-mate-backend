from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from common.api import PublicLookupMixin

from .models import Menu, MenuCategory, MenuItem
from .serializers import MenuCategorySerializer, MenuItemSerializer, MenuSerializer


@extend_schema(tags=["Menu"])
class MenuViewSet(PublicLookupMixin, viewsets.ReadOnlyModelViewSet[Menu]):
    queryset = Menu.objects.all()
    serializer_class = MenuSerializer


@extend_schema(tags=["Menu"])
class MenuCategoryViewSet(
    PublicLookupMixin, viewsets.ReadOnlyModelViewSet[MenuCategory]
):
    queryset = MenuCategory.objects.all()
    serializer_class = MenuCategorySerializer


@extend_schema(tags=["Menu"])
class MenuItemViewSet(PublicLookupMixin, viewsets.ReadOnlyModelViewSet[MenuItem]):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
