from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny

from apps.authentication.permissions import IsStaff
from common.api import (
    PublicLookupMixin,
    PublicRestaurantQueryMixin,
    RestaurantScopedViewSetMixin,
    get_restaurant_id_from_auth,
)

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


class _PublicRestaurantScopedViewSetMixin(PublicRestaurantQueryMixin):
    def get_restaurant_id(self) -> int | None:
        restaurant_id = get_restaurant_id_from_auth(self.request)  # type: ignore[attr-defined]
        if restaurant_id is not None:
            return restaurant_id
        return super().get_restaurant_id()


@extend_schema(tags=["Restaurants"])
class RestaurantSettingsViewSet(
    PublicLookupMixin,
    _PublicRestaurantScopedViewSetMixin,
    viewsets.ReadOnlyModelViewSet[RestaurantSettings],
):
    permission_classes = [AllowAny]
    queryset = RestaurantSettings.objects.all()
    serializer_class = RestaurantSettingsSerializer

    def get_queryset(self) -> QuerySet[RestaurantSettings]:
        qs = super().get_queryset()
        restaurant_id = self.get_restaurant_id()
        if restaurant_id is not None:
            return qs.filter(restaurant_id=restaurant_id)
        return qs.none()


@extend_schema(tags=["Restaurants"])
class TableViewSet(
    PublicLookupMixin,
    _PublicRestaurantScopedViewSetMixin,
    viewsets.ReadOnlyModelViewSet[Table],
):
    permission_classes = [AllowAny]
    queryset = Table.objects.all()
    serializer_class = TableSerializer
    filterset_fields = ["status", "capacity"]

    def get_queryset(self) -> QuerySet[Table]:
        qs = super().get_queryset()
        restaurant_id = self.get_restaurant_id()
        if restaurant_id is not None:
            return qs.filter(restaurant_id=restaurant_id)
        return qs.none()
