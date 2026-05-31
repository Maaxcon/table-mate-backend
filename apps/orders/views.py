from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.authentication.permissions import IsFloor, IsNonKitchen, IsStaff
from common.api import RestaurantScopedViewSetMixin, get_restaurant_id_from_auth

from .models import Order, OrderItem, Session, Ticket
from .selectors import get_customer_orders
from .serializers import (
    OrderItemSerializer,
    OrderSerializer,
    SessionSerializer,
    TicketSerializer,
)


@extend_schema(tags=["Orders"])
class SessionViewSet(
    RestaurantScopedViewSetMixin[Session],
    viewsets.ReadOnlyModelViewSet[Session],
):
    permission_classes = [IsFloor]
    queryset = Session.objects.all()
    serializer_class = SessionSerializer
    filterset_fields = ["table", "reservation", "opened_by", "status", "currency"]
    ordering_fields = ["created_at", "updated_at", "started_at", "closed_at"]


@extend_schema(tags=["Orders"])
class OrderViewSet(
    RestaurantScopedViewSetMixin[Order],
    viewsets.ReadOnlyModelViewSet[Order],
):
    permission_classes = [IsStaff]
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    filterset_fields = [
        "session",
        "created_by",
        "created_by_source",
        "source",
        "status",
        "payment_status",
        "currency",
    ]
    ordering_fields = ["created_at", "updated_at", "status", "payment_status"]

    @extend_schema(responses=OrderSerializer(many=True))
    @action(detail=False, methods=["get"], url_path="my", permission_classes=[IsNonKitchen])
    def my(self, request: Request) -> Response:
        restaurant_id = get_restaurant_id_from_auth(request)
        if restaurant_id is None:
            raise ValidationError("Restaurant context required.")
        orders = get_customer_orders(request.user.pk, restaurant_id=restaurant_id)  # type: ignore[arg-type]
        serializer = self.get_serializer(orders, many=True)
        return Response(serializer.data)


@extend_schema(tags=["Orders"])
class TicketViewSet(
    RestaurantScopedViewSetMixin[Ticket],
    viewsets.ReadOnlyModelViewSet[Ticket],
):
    permission_classes = [IsStaff]
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer
    filterset_fields = ["session", "order", "status"]
    ordering_fields = [
        "created_at",
        "updated_at",
        "injected_at",
        "started_at",
        "completed_at",
    ]


@extend_schema(tags=["Orders"])
class OrderItemViewSet(
    RestaurantScopedViewSetMixin[OrderItem],
    viewsets.ReadOnlyModelViewSet[OrderItem],
):
    permission_classes = [IsStaff]
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    filterset_fields = [
        "order",
        "ticket",
        "menu_item",
        "status",
        "voided_by",
        "void_reason",
        "is_wasted",
    ]
    ordering_fields = ["created_at", "updated_at", "guest_slot", "status", "voided_at"]
