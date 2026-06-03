from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.permissions import SAFE_METHODS, AllowAny, BasePermission
from rest_framework.serializers import BaseSerializer

from apps.authentication.models import RoleCode, User
from apps.authentication.permissions import IsAdmin, IsStaff
from common.api import (
    PublicLookupMixin,
    PublicRestaurantQueryMixin,
    RestaurantScopedViewSetMixin,
    get_restaurant_id_from_auth,
)

from . import services
from .models import Restaurant, RestaurantSettings, Table, Zone
from .serializers import (
    BookingSettingsSerializer,
    EmployeeCreateSerializer,
    EmployeeSerializer,
    PublicRestaurantSerializer,
    RestaurantSerializer,
    RestaurantSettingsSerializer,
    TableSerializer,
    ZoneSerializer,
)


@extend_schema(tags=["Restaurants"])
class PublicRestaurantViewSet(
    PublicLookupMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet[Restaurant],
):
    queryset = Restaurant.objects.select_related("settings").all()
    serializer_class = PublicRestaurantSerializer
    permission_classes = [AllowAny]


@extend_schema(tags=["Restaurants"])
class RestaurantViewSet(
    RestaurantScopedViewSetMixin[Restaurant],
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet[Restaurant],
):
    queryset = Restaurant.objects.all()
    serializer_class = RestaurantSerializer
    restaurant_lookup = "id"
    ordering_fields = ["created_at", "updated_at", "name"]
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self) -> list[BasePermission]:
        if self.request.method in SAFE_METHODS:
            return [IsStaff()]
        return [IsAdmin()]

    def perform_update(self, serializer: BaseSerializer[Restaurant]) -> None:
        services.update_restaurant(serializer.instance, **serializer.validated_data)


class _PublicRestaurantScopedViewSetMixin(PublicRestaurantQueryMixin):
    def get_restaurant_id(self) -> int | None:
        restaurant_id = get_restaurant_id_from_auth(self.request)  # type: ignore[attr-defined]
        if restaurant_id is not None:
            return restaurant_id
        return super().get_restaurant_id()


@extend_schema(tags=["Restaurants"])
class ZoneViewSet(
    PublicLookupMixin,
    _PublicRestaurantScopedViewSetMixin,
    viewsets.ReadOnlyModelViewSet[Zone],
):
    permission_classes = [AllowAny]
    queryset = Zone.objects.all()
    serializer_class = ZoneSerializer

    def get_queryset(self) -> QuerySet[Zone]:
        qs = super().get_queryset()
        restaurant_id = self.get_restaurant_id()
        if restaurant_id is not None:
            return qs.filter(restaurant_id=restaurant_id)
        return qs.none()


@extend_schema(tags=["Restaurants"])
class RestaurantSettingsViewSet(
    PublicLookupMixin,
    _PublicRestaurantScopedViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet[RestaurantSettings],
):
    queryset = RestaurantSettings.objects.all()
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self) -> list[BasePermission]:
        if self.request.method in SAFE_METHODS:
            return [AllowAny()]
        return [IsAdmin()]

    def get_serializer_class(self) -> type[BaseSerializer[RestaurantSettings]]:
        # Anonymous booking clients get the trimmed booking fields; admins
        # editing settings get the full serializer.
        if self.request.method in SAFE_METHODS:
            return BookingSettingsSerializer
        return RestaurantSettingsSerializer

    def get_queryset(self) -> QuerySet[RestaurantSettings]:
        qs = super().get_queryset()
        restaurant_id = self.get_restaurant_id()
        if restaurant_id is not None:
            return qs.filter(restaurant_id=restaurant_id)
        return qs.none()

    def perform_update(self, serializer: BaseSerializer[RestaurantSettings]) -> None:
        services.update_restaurant_settings(serializer.instance, **serializer.validated_data)


@extend_schema(tags=["Restaurants"])
class EmployeeViewSet(
    RestaurantScopedViewSetMixin[User],
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet[User],
):
    permission_classes = [IsAdmin]
    queryset = User.objects.all()
    serializer_class = EmployeeSerializer
    filterset_fields = ["role", "is_active"]
    ordering_fields = ["role", "email", "created_at", "updated_at"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_serializer_class(self) -> type[BaseSerializer[User]]:
        if self.action == "create":
            return EmployeeCreateSerializer
        return EmployeeSerializer

    def safely_get_queryset(self, qs):  # type: ignore[no-untyped-def]
        return qs.exclude(role=RoleCode.CUSTOMER)

    def perform_create(self, serializer: BaseSerializer[User]) -> None:
        # Restaurant comes from the admin's auth context, never the request body,
        # so an admin can only add staff to their own restaurant.
        restaurant_id = get_restaurant_id_from_auth(self.request)
        serializer.instance = services.create_employee(
            restaurant_id=restaurant_id,
            **serializer.validated_data,
        )

    def perform_update(self, serializer: BaseSerializer[User]) -> None:
        services.manage_employee(serializer.instance, **serializer.validated_data)


@extend_schema(tags=["Restaurants"])
class TableViewSet(
    PublicLookupMixin,
    _PublicRestaurantScopedViewSetMixin,
    viewsets.ReadOnlyModelViewSet[Table],
):
    permission_classes = [AllowAny]
    queryset = Table.objects.select_related("zone").all()
    serializer_class = TableSerializer
    filterset_fields = ["status", "capacity", "zone__public_id"]

    def get_queryset(self) -> QuerySet[Table]:
        qs = super().get_queryset()
        restaurant_id = self.get_restaurant_id()
        if restaurant_id is not None:
            return qs.filter(restaurant_id=restaurant_id)
        return qs.none()
