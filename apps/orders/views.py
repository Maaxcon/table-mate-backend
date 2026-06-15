from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.request import Request
from rest_framework.response import Response

from apps.authentication.permissions import IsFloor, IsStaff
from common.api import RestaurantScopedViewSetMixin, get_restaurant_id_from_auth
from common.hall_events import emit_hall_table_status_changed

from .models import Order, OrderItem, Session, SessionStatus, Ticket
from .serializers import (
    OrderItemSerializer,
    OrderSerializer,
    SessionSerializer,
    TicketSerializer,
)


@extend_schema(tags=["Orders"])
class SessionViewSet(
    RestaurantScopedViewSetMixin[Session],
    viewsets.ModelViewSet[Session],
):
    permission_classes = [IsFloor]
    queryset = Session.objects.all()
    serializer_class = SessionSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["table", "table__public_id", "reservation", "opened_by", "status", "currency"]
    ordering_fields = ["created_at", "updated_at", "opened_at"]

    def perform_create(self, serializer):  # type: ignore[no-untyped-def]
        instance = serializer.save(
            restaurant_id=get_restaurant_id_from_auth(self.request),
            opened_by=self.request.user,
        )
        table = instance.table
        if table:
            emit_hall_table_status_changed(
                instance.restaurant_id,
                table_id=str(table.public_id),
                previous_status="free",
                current_status="occupied",
                session_id=str(instance.public_id),
                actor=self.request.user,  # type: ignore[arg-type]
            )

    def partial_update(self, request: Request, *args: object, **kwargs: object) -> Response:
        instance = self.get_object()
        previous_status = instance.status

        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        instance.refresh_from_db()

        if previous_status == SessionStatus.OPEN and instance.status != SessionStatus.OPEN:
            table = instance.table
            if table:
                emit_hall_table_status_changed(
                    instance.restaurant_id,
                    table_id=str(table.public_id),
                    previous_status="occupied",
                    current_status="free",
                    session_id=str(instance.public_id),
                    actor=request.user,  # type: ignore[arg-type]
                )

        return Response(serializer.data)


@extend_schema(tags=["Orders"])
class OrderViewSet(
    RestaurantScopedViewSetMixin[Order],
    viewsets.ModelViewSet[Order],
):
    permission_classes = [IsStaff]
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = [
        "session",
        "session__public_id",
        "created_by",
        "created_by_source",
        "source",
        "status",
        "payment_status",
        "currency",
    ]
    ordering_fields = ["created_at", "updated_at", "status", "payment_status"]

    def perform_create(self, serializer):  # type: ignore[no-untyped-def]
        serializer.save(
            restaurant_id=get_restaurant_id_from_auth(self.request),
            created_by=self.request.user,
        )


@extend_schema(tags=["Orders"])
class TicketViewSet(
    RestaurantScopedViewSetMixin[Ticket],
    viewsets.ModelViewSet[Ticket],
):
    permission_classes = [IsStaff]
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["session", "order", "status"]
    ordering_fields = [
        "created_at",
        "updated_at",
        "injected_at",
        "started_at",
        "completed_at",
    ]

    def perform_create(self, serializer):  # type: ignore[no-untyped-def]
        serializer.save(restaurant_id=get_restaurant_id_from_auth(self.request))


@extend_schema(tags=["Orders"])
class OrderItemViewSet(
    RestaurantScopedViewSetMixin[OrderItem],
    viewsets.ModelViewSet[OrderItem],
):
    permission_classes = [IsStaff]
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = [
        "order",
        "order__public_id",
        "ticket",
        "menu_item",
        "status",
        "voided_by",
        "void_reason",
        "is_wasted",
    ]
    ordering_fields = ["created_at", "updated_at", "guest_slot", "status", "voided_at"]

    def perform_create(self, serializer):  # type: ignore[no-untyped-def]
        serializer.save(restaurant_id=get_restaurant_id_from_auth(self.request))
