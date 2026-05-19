from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from .models import Restaurant, RestaurantSettings, Table
from .serializers import (
    RestaurantSerializer,
    RestaurantSettingsSerializer,
    TableSerializer,
)


@extend_schema(tags=["Restaurants"])
class RestaurantViewSet(viewsets.ReadOnlyModelViewSet[Restaurant]):
    queryset = Restaurant.objects.all()
    serializer_class = RestaurantSerializer


@extend_schema(tags=["Restaurants"])
class RestaurantSettingsViewSet(viewsets.ReadOnlyModelViewSet[RestaurantSettings]):
    queryset = RestaurantSettings.objects.all()
    serializer_class = RestaurantSettingsSerializer


@extend_schema(tags=["Restaurants"])
class TableViewSet(viewsets.ReadOnlyModelViewSet[Table]):
    queryset = Table.objects.all()
    serializer_class = TableSerializer
