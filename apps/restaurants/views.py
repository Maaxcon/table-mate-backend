from io import BytesIO
from typing import Any, cast

import qrcode
from django.db import transaction
from django.db.models import ProtectedError, QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import SAFE_METHODS, AllowAny, BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView

from apps.authentication.models import RoleCode, User
from apps.authentication.permissions import IsAdmin, IsStaff
from apps.menu.models import Menu, MenuCategory, MenuItem
from apps.reservations.services import activate_reservation_by_scan
from common.api import (
    PublicLookupMixin,
    PublicRestaurantQueryMixin,
    RestaurantScopedViewSetMixin,
    get_restaurant_id_from_auth,
    require_restaurant_id_from_auth,
)
from common.hall_events import (
    emit_hall_zone_created,
    emit_hall_zone_deleted,
    emit_hall_zone_updated,
)
from common.renderers import PNGRenderer

from . import selectors, services
from .models import Restaurant, RestaurantSettings, Table, Zone
from .serializers import (
    AdminOverviewSerializer,
    BookingSettingsSerializer,
    EmployeeCreateSerializer,
    EmployeeSerializer,
    LayoutResponseSerializer,
    PublicRestaurantSerializer,
    RestaurantSerializer,
    RestaurantSettingsSerializer,
    TableSerializer,
    VerifyScanResponseSerializer,
    ZoneSerializer,
)


@extend_schema(tags=["Restaurants"], responses=AdminOverviewSerializer)
class AdminOverviewView(APIView):
    """Aggregate counts for the admin dashboard, in one request."""

    permission_classes = [IsAdmin]

    def get(self, request: Request) -> Response:
        restaurant_id = get_restaurant_id_from_auth(request)
        if restaurant_id is None:
            return Response(
                {
                    "menus_total": 0,
                    "menus_active": 0,
                    "dishes_total": 0,
                    "dishes_hidden": 0,
                    "categories_total": 0,
                    "staff_total": 0,
                    "staff_active": 0,
                }
            )

        menus = Menu.objects.filter(restaurant_id=restaurant_id)
        items = MenuItem.objects.filter(restaurant_id=restaurant_id)
        categories = MenuCategory.objects.filter(menu__restaurant_id=restaurant_id)
        staff = User.objects.filter(restaurant_id=restaurant_id).exclude(role=RoleCode.CUSTOMER)

        data = {
            "menus_total": menus.count(),
            "menus_active": menus.filter(is_active=True).count(),
            "dishes_total": items.count(),
            "dishes_hidden": items.filter(is_available=False).count(),
            "categories_total": categories.count(),
            "staff_total": staff.count(),
            "staff_active": staff.filter(is_active=True).count(),
        }
        return Response(AdminOverviewSerializer(data).data)


@extend_schema(tags=["Restaurants"])
class VerifyTableScanView(APIView):
    permission_classes = [AllowAny]
    serializer_class = None

    @extend_schema(
        summary="Verify a table QR scan",
        description="Checks for an imminent PENDING reservation for the scanned table. "
        "Requires authentication. If found and owned by the caller, flips the reservation to ACTIVE.",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "table_id": {"type": "string", "format": "uuid", "description": "Table public ID"},
                },
                "required": ["table_id"],
            }
        },
        responses={200: VerifyScanResponseSerializer, 401: VerifyScanResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        table_id = request.data.get("table_id")
        if not table_id:
            raise ValidationError("table_id is required.")

        try:
            table = Table.objects.get(public_id=table_id, active=True)
        except Table.DoesNotExist:
            raise ValidationError("Table not found.") from None

        valid, detail = activate_reservation_by_scan(table=table, user=request.user)

        if not valid and "Authentication" in detail:
            return Response({"valid": False, "detail": detail}, status=401)

        return Response({"valid": valid, "detail": detail})


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
        data = dict(serializer.validated_data)
        working_hours = data.pop("working_hours", None)
        # One transaction so a failure on the settings write rolls back the profile write.
        with transaction.atomic():
            restaurant = services.update_restaurant(cast(Restaurant, serializer.instance), **data)
            if working_hours is not None:
                settings, _ = RestaurantSettings.objects.get_or_create(restaurant=restaurant)
                services.update_restaurant_settings(settings, working_hours=working_hours)

    @extend_schema(request=None, responses=RestaurantSerializer)
    @action(
        detail=True,
        methods=["patch"],
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def cover(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Set the cover from `cover_image`, or clear it when that key is sent empty."""
        restaurant = self.get_object()
        file = request.FILES.get("cover_image")
        if file is not None:
            restaurant.cover_image = file
        elif "cover_image" in request.data:
            restaurant.cover_image = None
        else:
            return Response(RestaurantSerializer(restaurant, context=self.get_serializer_context()).data)
        restaurant.save(update_fields=["cover_image", "updated_at"])
        return Response(RestaurantSerializer(restaurant, context=self.get_serializer_context()).data)


class _PublicRestaurantScopedViewSetMixin(PublicRestaurantQueryMixin):
    def get_restaurant_id(self) -> int | None:
        user = getattr(self.request, "user", None)  # type: ignore[attr-defined]
        if user is not None and user.is_authenticated and user.role != RoleCode.CUSTOMER:
            restaurant_id = get_restaurant_id_from_auth(self.request)  # type: ignore[attr-defined]
            if restaurant_id is not None:
                return restaurant_id
        return super().get_restaurant_id()


@extend_schema(tags=["Restaurants"])
class ZoneViewSet(
    PublicLookupMixin,
    _PublicRestaurantScopedViewSetMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.ReadOnlyModelViewSet[Zone],
):
    queryset = Zone.objects.all()
    serializer_class = ZoneSerializer

    def get_permissions(self) -> list[BasePermission]:
        if self.request.method in SAFE_METHODS:
            return [AllowAny()]
        return [IsAdmin()]

    def get_queryset(self) -> QuerySet[Zone]:
        qs = super().get_queryset()
        restaurant_id = self.get_restaurant_id()
        if restaurant_id is not None:
            return qs.filter(restaurant_id=restaurant_id)
        return qs.none()

    def perform_create(self, serializer: BaseSerializer[Zone]) -> None:
        restaurant_id = self.get_restaurant_id()
        if restaurant_id is None:
            raise ValidationError("Restaurant is required to create a zone")
        zone = serializer.save(restaurant_id=restaurant_id)
        transaction.on_commit(
            lambda: emit_hall_zone_created(
                restaurant_id=restaurant_id,
                zone_public_id=str(zone.public_id),
                zone_name=zone.name,
            )
        )

    def perform_update(self, serializer: BaseSerializer[Zone]) -> None:
        zone = serializer.save()
        transaction.on_commit(
            lambda: emit_hall_zone_updated(
                restaurant_id=zone.restaurant_id,
                zone_public_id=str(zone.public_id),
                zone_name=zone.name,
                zone_updated_at=zone.updated_at.isoformat(),
            )
        )

    def perform_destroy(self, instance: Zone) -> None:
        public_id = str(instance.public_id)
        restaurant_id = instance.restaurant_id
        instance.delete()
        transaction.on_commit(
            lambda: emit_hall_zone_deleted(
                restaurant_id=restaurant_id,
                zone_public_id=public_id,
            )
        )

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"detail": "This zone still has tables. Reassign or remove them before deleting."},
                status=status.HTTP_400_BAD_REQUEST,
            )


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
        services.update_restaurant_settings(cast(RestaurantSettings, serializer.instance), **serializer.validated_data)


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
        restaurant_id = require_restaurant_id_from_auth(self.request)
        serializer.instance = services.create_employee(
            restaurant_id=restaurant_id,
            **serializer.validated_data,
        )

    def perform_update(self, serializer: BaseSerializer[User]) -> None:
        employee = cast(User, serializer.instance)
        self._guard_last_admin(employee, serializer.validated_data)
        services.manage_employee(employee, **serializer.validated_data)

    def _guard_last_admin(self, employee: User, data: dict[str, Any]) -> None:
        """Block a change that would leave the restaurant with no active admin."""
        restaurant_id = employee.restaurant_id
        if restaurant_id is None:
            return
        if not (employee.role == RoleCode.ADMIN and employee.is_active):
            return
        new_role = data.get("role", employee.role)
        new_active = data.get("is_active", employee.is_active)
        if new_role == RoleCode.ADMIN and new_active:
            return
        other_active_admin = (
            User.objects.filter(
                restaurant_id=restaurant_id,
                role=RoleCode.ADMIN,
                is_active=True,
            )
            .exclude(pk=employee.pk)
            .exists()
        )
        if not other_active_admin:
            raise ValidationError("You cannot demote or deactivate the last active admin.")


@extend_schema(tags=["Restaurants"])
class TableViewSet(
    PublicLookupMixin,
    _PublicRestaurantScopedViewSetMixin,
    viewsets.ReadOnlyModelViewSet[Table],
):
    permission_classes = [AllowAny]
    queryset = Table.objects.select_related("zone").all()
    serializer_class = TableSerializer
    filterset_fields = ["capacity", "zone__public_id"]

    def get_permissions(self) -> list[BasePermission]:
        if self.action == "qr":
            return [IsAdmin()]
        return [AllowAny()]

    def get_queryset(self) -> QuerySet[Table]:
        restaurant_id = self.get_restaurant_id()
        if restaurant_id is None:
            return Table.objects.none()
        return selectors.get_tables_with_occupancy(restaurant_id)

    @extend_schema(
        summary="Tables layout with upcoming reservations",
        description=(
            "Returns all active tables, the latest layout JSON, and today's PENDING reservations for the floor plan."
        ),
        responses=LayoutResponseSerializer,
    )
    @action(detail=False, methods=["get"])
    def layout(self, request: Request) -> Response:
        restaurant_id = self.get_restaurant_id()
        if restaurant_id is None:
            return Response({"tables": [], "layout": None, "upcoming_reservations": []})

        tables_qs = self.get_queryset().filter(active=True)
        tables_serializer = self.get_serializer(tables_qs, many=True)

        from apps.editor.models import LayoutVersion

        latest_layout = (
            LayoutVersion.objects.filter(restaurant_id=restaurant_id).order_by("-published_at", "-id").first()
        )
        layout_payload = latest_layout.layout_json if latest_layout else None

        layout_data = selectors.get_layout_data(restaurant_id)

        return Response(
            {
                "tables": tables_serializer.data,
                "layout": layout_payload,
                "upcoming_reservations": layout_data["upcoming_reservations"],
            }
        )

    @extend_schema(
        summary="QR code image for a table",
        description="Returns a PNG QR code. Scanning it opens this table's menu page.",
        responses={200: OpenApiTypes.BINARY},
    )
    @action(detail=True, methods=["get"], renderer_classes=[PNGRenderer])
    def qr(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # Deliberately bypasses get_object()/get_queryset(): those fall back to
        # the public `?restaurant=` query param when the caller's JWT has no
        # restaurant_id claim (e.g. a superuser account), which would let this
        # admin-only action serve another restaurant's table. Require the
        # claim directly instead, so scoping can't be steered by the request.
        restaurant_id = require_restaurant_id_from_auth(request)
        table = get_object_or_404(
            Table.objects.select_related("restaurant"),
            public_id=kwargs["public_id"],
            restaurant_id=restaurant_id,
        )
        url = services.build_table_menu_url(table)
        image = qrcode.make(url)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return Response(buffer.getvalue(), content_type="image/png")
