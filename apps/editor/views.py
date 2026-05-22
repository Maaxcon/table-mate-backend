from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.restaurants.models import Table
from common.api import RestaurantScopedViewSetMixin
from common.permissions import HasAnyRole

from .models import Layout
from .selectors import get_available_tables
from .serializers import EditorTableSerializer, LayoutSerializer


@extend_schema(tags=["Editor"])
class LayoutViewSet(RestaurantScopedViewSetMixin[Layout], viewsets.ReadOnlyModelViewSet[Layout]):
    queryset = Layout.objects.all()
    serializer_class = LayoutSerializer
    filterset_fields = ["version", "published_at", "published_by"]
    ordering_fields = ["created_at", "updated_at", "version", "published_at"]


@extend_schema(tags=["Editor"])
class EditorTableViewSet(
    RestaurantScopedViewSetMixin[Table],
    viewsets.ModelViewSet[Table],
):
    queryset = Table.objects.all()
    serializer_class = EditorTableSerializer
    http_method_names = ["get", "patch", "head", "options"]
    filterset_fields = ["status", "capacity", "shape", "active"]
    ordering_fields = [
        "created_at",
        "updated_at",
        "table_number",
        "capacity",
        "status",
    ]

    def safely_get_queryset(self, qs: QuerySet[Table]) -> QuerySet[Table]:
        return qs.filter(active=True)

    def get_permissions(self) -> list[BasePermission]:
        if self.action == "available":
            return [IsAuthenticated()]
        return [IsAuthenticated(), HasAnyRole.with_roles("admin", "waiter")]

    @action(detail=False, methods=["get"], url_path="available")
    def available(self, request: Request) -> Response:
        auth = getattr(request, "auth", None)
        restaurant_id = None
        if auth is not None and hasattr(auth, "get"):
            restaurant_id = auth.get("restaurant_id")

        if restaurant_id is None:
            return Response(
                {"detail": "Restaurant context required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_at = request.query_params.get("start_at")
        end_at = request.query_params.get("end_at")
        guest_count = request.query_params.get("guest_count")

        if not start_at or not end_at:
            return Response(
                {"detail": "start_at and end_at query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from datetime import datetime

        try:
            start_dt = datetime.fromisoformat(start_at)
            end_dt = datetime.fromisoformat(end_at)
        except (ValueError, TypeError):
            return Response(
                {"detail": "Invalid date format. Use ISO 8601."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        gc = int(guest_count) if guest_count else None
        tables = get_available_tables(
            restaurant_id=int(restaurant_id),
            start_at=start_dt,
            end_at=end_dt,
            guest_count=gc,
        )
        serializer = self.get_serializer(tables, many=True)
        return Response(serializer.data)
