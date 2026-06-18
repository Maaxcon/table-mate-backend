from datetime import datetime

from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.authentication.models import RoleCode
from apps.authentication.permissions import IsAdmin, IsFloor
from apps.reservations.models import Reservation
from apps.restaurants.models import Restaurant, Table
from common.api import (
    PublicLookupMixin,
    PublicRestaurantQueryMixin,
    RestaurantScopedViewSetMixin,
    get_restaurant_id_from_auth,
    require_restaurant_id_from_auth,
)
from common.permissions import HasAnyRole

from .models import Layout
from .selectors import get_available_tables
from .serializers import (
    EditorTableSerializer,
    LayoutSerializer,
    LayoutVersionSerializer,
    PublishLayoutSerializer,
)
from .services import publish_layout, update_table_position


@extend_schema(tags=["Editor"])
class LayoutViewSet(RestaurantScopedViewSetMixin[Layout], viewsets.ReadOnlyModelViewSet[Layout]):
    permission_classes = [IsFloor]
    queryset = Layout.objects.all()
    serializer_class = LayoutSerializer
    filterset_fields = ["version", "published_at", "published_by"]
    ordering_fields = ["created_at", "updated_at", "version", "published_at"]

    @extend_schema(
        request=PublishLayoutSerializer,
        responses={201: LayoutVersionSerializer},
    )
    @action(detail=False, methods=["post"], permission_classes=[IsAdmin])
    def publish(self, request: Request) -> Response:
        restaurant_id = require_restaurant_id_from_auth(request)
        serializer = PublishLayoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = publish_layout(
            restaurant_id=restaurant_id,
            layout_json=serializer.validated_data["layout_json"],
            published_by=request.user,  # type: ignore[arg-type]  # IsAdmin guarantees authenticated user
        )
        version = result["version"]
        output = LayoutVersionSerializer(version)
        return Response(
            {
                **output.data,
                "table_id_map": result["table_id_map"],
                "warnings": result["warnings"],
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Editor"])
class EditorTableViewSet(
    PublicLookupMixin,
    PublicRestaurantQueryMixin,
    viewsets.ModelViewSet[Table],
):
    queryset = Table.objects.all()
    serializer_class = EditorTableSerializer
    http_method_names = ["get", "patch", "head", "options"]
    filterset_fields = ["capacity", "shape", "active"]
    ordering_fields = [
        "created_at",
        "updated_at",
        "table_number",
        "capacity",
    ]

    def get_queryset(self) -> QuerySet[Table]:
        qs = super().get_queryset()
        restaurant_id = get_restaurant_id_from_auth(self.request)
        if restaurant_id is not None:
            qs = qs.filter(restaurant_id=restaurant_id)
        return qs.filter(active=True)

    def get_permissions(self) -> list[BasePermission]:
        if self.action == "available":
            return []
        return [IsAuthenticated(), HasAnyRole.with_roles(RoleCode.ADMIN, RoleCode.WAITER)]

    def _resolve_restaurant_id(self, request: Request) -> int | None:
        restaurant_id = get_restaurant_id_from_auth(request)
        if restaurant_id is not None:
            return restaurant_id
        public_id = request.query_params.get(self.restaurant_query_param)
        if public_id:
            try:
                return Restaurant.objects.values_list("id", flat=True).get(public_id=public_id)
            except Restaurant.DoesNotExist:
                pass
        return None

    @extend_schema(
        responses=EditorTableSerializer(many=True),
        parameters=[
            OpenApiParameter(name="start_at", type=str, required=True, description="ISO 8601 datetime"),
            OpenApiParameter(name="end_at", type=str, required=True, description="ISO 8601 datetime"),
            OpenApiParameter(name="guest_count", type=int, required=False),
            OpenApiParameter(
                name="exclude",
                type=str,
                required=False,
                description="Reservation public ID to exclude when checking an existing booking.",
            ),
            OpenApiParameter(
                name="restaurant",
                type=str,
                required=False,
                description="Restaurant public ID for unauthenticated access",
            ),
        ],
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="available",
        filter_backends=[],
        authentication_classes=[],
    )
    def available(self, request: Request) -> Response:
        restaurant_id = self._resolve_restaurant_id(request)

        if restaurant_id is None:
            return Response(
                {"detail": "Restaurant context required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_at = request.query_params.get("start_at")
        end_at = request.query_params.get("end_at")
        guest_count = request.query_params.get("guest_count")
        exclude_public_id = request.query_params.get("exclude")

        if not start_at or not end_at:
            return Response(
                {"detail": "start_at and end_at query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            start_dt = datetime.fromisoformat(start_at)
            end_dt = datetime.fromisoformat(end_at)
        except (ValueError, TypeError):
            return Response(
                {"detail": "Invalid date format. Use ISO 8601."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if start_dt >= end_dt:
            return Response(
                {"detail": "start_at must be before end_at."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            gc = int(guest_count) if guest_count else None
        except ValueError:
            return Response({"detail": "guest_count must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
        current_reservation_id = None
        if exclude_public_id:
            current_reservation_id = (
                Reservation.objects.filter(
                    public_id=exclude_public_id,
                    restaurant_id=restaurant_id,
                )
                .values_list("id", flat=True)
                .first()
            )
        tables = get_available_tables(
            restaurant_id=restaurant_id,
            start_at=start_dt,
            end_at=end_dt,
            guest_count=gc,
            current_reservation_id=current_reservation_id,
        )
        serializer = self.get_serializer(tables, many=True)
        return Response(serializer.data)

    def partial_update(self, request: Request, *args: object, **kwargs: object) -> Response:
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        update_table_position(
            instance,
            position_x=serializer.validated_data.get("position_x"),
            position_y=serializer.validated_data.get("position_y"),
        )

        result_serializer = self.get_serializer(instance)
        return Response(result_serializer.data)
