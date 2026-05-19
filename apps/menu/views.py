from rest_framework import viewsets

from .models import Menu, MenuCategory, MenuItem
from .serializers import MenuCategorySerializer, MenuItemSerializer, MenuSerializer


class MenuViewSet(viewsets.ReadOnlyModelViewSet[Menu]):
    queryset = Menu.objects.all()
    serializer_class = MenuSerializer


class MenuCategoryViewSet(viewsets.ReadOnlyModelViewSet[MenuCategory]):
    queryset = MenuCategory.objects.all()
    serializer_class = MenuCategorySerializer


class MenuItemViewSet(viewsets.ReadOnlyModelViewSet[MenuItem]):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
