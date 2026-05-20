from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from common.api import RestaurantScopedViewSetMixin

from .models import Order, OrderItem, Session, Ticket
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
    queryset = Session.objects.all()
    serializer_class = SessionSerializer
    filterset_fields = ["table", "reservation", "opened_by", "status", "currency"]
    ordering_fields = ["created_at", "updated_at", "started_at", "closed_at"]


@extend_schema(tags=["Orders"])
class OrderViewSet(
    RestaurantScopedViewSetMixin[Order],
    viewsets.ReadOnlyModelViewSet[Order],
):
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


@extend_schema(tags=["Orders"])
class TicketViewSet(
    RestaurantScopedViewSetMixin[Ticket],
    viewsets.ReadOnlyModelViewSet[Ticket],
):
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
