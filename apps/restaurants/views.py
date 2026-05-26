from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny

from apps.authentication.permissions import IsAdmin, IsFloor, IsStaff
from common.api import PublicLookupMixin, RestaurantScopedViewSetMixin

from .models import Restaurant, RestaurantSettings, Table
from .serializers import (
    PublicRestaurantSerializer,
    RestaurantSerializer,
    RestaurantSettingsSerializer,
    TableSerializer,
)


@extend_schema(tags=["Restaurants"])
class PublicRestaurantViewSet(
    PublicLookupMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet[Restaurant],
):
    queryset = Restaurant.objects.select_related("settings").all()
    serializer_class = PublicRestaurantSerializer
    permission_classes = [AllowAny]


@extend_schema(tags=["Restaurants"])
class RestaurantViewSet(
    RestaurantScopedViewSetMixin[Restaurant],
    viewsets.ReadOnlyModelViewSet[Restaurant],
):
    permission_classes = [IsStaff]
    queryset = Restaurant.objects.all()
    serializer_class = RestaurantSerializer
    restaurant_lookup = "id"
    ordering_fields = ["created_at", "updated_at", "name"]


@extend_schema(tags=["Restaurants"])
class RestaurantSettingsViewSet(
    RestaurantScopedViewSetMixin[RestaurantSettings],
    viewsets.ReadOnlyModelViewSet[RestaurantSettings],
):
    permission_classes = [IsAdmin]
    queryset = RestaurantSettings.objects.all()
    serializer_class = RestaurantSettingsSerializer
    filterset_fields = ["restaurant", "timezone", "currency", "locale"]
    ordering_fields = ["created_at", "updated_at", "timezone", "currency", "locale"]


@extend_schema(tags=["Restaurants"])
class TableViewSet(
    RestaurantScopedViewSetMixin[Table],
    viewsets.ReadOnlyModelViewSet[Table],
):
    permission_classes = [IsFloor]
    queryset = Table.objects.all()
    serializer_class = TableSerializer
    filterset_fields = ["status", "capacity"]
    ordering_fields = ["created_at", "updated_at", "table_number", "capacity", "status"]
