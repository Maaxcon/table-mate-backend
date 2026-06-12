from datetime import timedelta
from typing import Any, cast

from django.db import transaction
from django.db.models import Exists, OuterRef, QuerySet
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
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
from apps.orders.models import Session, SessionStatus
from apps.reservations.models import Reservation, ReservationStatus
from common.api import (
    PublicLookupMixin,
    PublicRestaurantQueryMixin,
    RestaurantScopedViewSetMixin,
    get_restaurant_id_from_auth,
    require_restaurant_id_from_auth,
)

from . import services
from .models import Restaurant, RestaurantSettings, Table, Zone
from .serializers import (
    AdminOverviewSerializer,
    BookingSettingsSerializer,
    EmployeeCreateSerializer,
    EmployeeSerializer,
    PublicRestaurantSerializer,
    RestaurantSerializer,
    RestaurantSettingsSerializer,
    TableSerializer,
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
        "If found and owned by the user, flips the reservation to ACTIVE.",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "table_id": {"type": "string", "format": "uuid", "description": "Table public ID"},
                },
                "required": ["table_id"],
            }
        },
    )
    def post(self, request: Request) -> Response:
        table_id = request.data.get("table_id")
        if not table_id:
            raise ValidationError("table_id is required.")

        try:
            table = Table.objects.get(public_id=table_id, active=True)
        except Table.DoesNotExist:
            raise ValidationError("Table not found.") from None

        now = timezone.now()
        deadline = now + timedelta(minutes=15)

        reservation = Reservation.objects.filter(
            table=table,
            status=ReservationStatus.PENDING,
            start_at__gte=now,
            start_at__lte=deadline,
        ).first()

        if not reservation:
            return Response(
                {"valid": False, "detail": "No imminent reservation found for this table."},
            )

        user = request.user
        if user.is_authenticated and reservation.customer_id != user.pk:
            return Response(
                {"valid": False, "detail": "This reservation belongs to another guest."},
            )

        reservation.status = ReservationStatus.ACTIVE
        reservation.save(update_fields=["status"])

        return Response({"valid": True, "detail": "Table verified and activated."})


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

    def get_queryset(self) -> QuerySet[Table]:
        qs = super().get_queryset()
        restaurant_id = self.get_restaurant_id()
        if restaurant_id is not None:
            qs = qs.filter(restaurant_id=restaurant_id)
        else:
            return qs.none()

        occupied_subquery = Session.objects.filter(
            table=OuterRef("pk"),
            status=SessionStatus.OPEN,
            reservation__status="active",
        )
        return qs.annotate(is_occupied=Exists(occupied_subquery))

    @extend_schema(
        summary="Tables layout with upcoming reservations",
        description="Returns all active tables and today's PENDING reservations for the floor plan.",
    )
    @action(detail=False, methods=["get"])
    def layout(self, request: Request) -> Response:
        restaurant_id = self.get_restaurant_id()
        if restaurant_id is None:
            return Response({"tables": [], "upcoming_reservations": []})

        tables_qs = self.get_queryset().filter(active=True)
        tables_serializer = self.get_serializer(tables_qs, many=True)

        now = timezone.now()
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        reservations = Reservation.objects.filter(
            restaurant_id=restaurant_id,
            status=ReservationStatus.PENDING,
            start_at__gte=now,
            start_at__lte=today_end,
        ).select_related("table")

        upcoming_reservations = [
            {
                "public_id": r.public_id,
                "table_id": r.table.public_id,
                "start_at": r.start_at,
            }
            for r in reservations
            if r.table is not None
        ]

        return Response(
            {
                "tables": tables_serializer.data,
                "upcoming_reservations": upcoming_reservations,
            }
        )
