from rest_framework import viewsets

from .models import Restaurant, RestaurantSettings, Table
from .serializers import (
    RestaurantSerializer,
    RestaurantSettingsSerializer,
    TableSerializer,
)


class RestaurantViewSet(viewsets.ReadOnlyModelViewSet[Restaurant]):
    queryset = Restaurant.objects.all()
    serializer_class = RestaurantSerializer


class RestaurantSettingsViewSet(viewsets.ReadOnlyModelViewSet[RestaurantSettings]):
    queryset = RestaurantSettings.objects.all()
    serializer_class = RestaurantSettingsSerializer


class TableViewSet(viewsets.ReadOnlyModelViewSet[Table]):
    queryset = Table.objects.all()
    serializer_class = TableSerializer
