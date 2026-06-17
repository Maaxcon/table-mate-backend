from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from apps.authentication.permissions import IsFloor, IsStaff
from apps.restaurants.models import RestaurantSettings
from common.api import RestaurantScopedViewSetMixin, get_restaurant_id_from_auth
from common.exceptions import TableOccupiedError

from .models import Order, OrderItem, Session, SessionStatus, Ticket
from .serializers import (
    OrderItemSerializer,
    OrderSerializer,
    SessionSerializer,
    TicketSerializer,
)
from .services import create_walk_in_reservation


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
        table = serializer.validated_data["table"]
        if Session.objects.filter(table=table, status=SessionStatus.OPEN).exists():
            raise TableOccupiedError()
        guest_count = serializer.validated_data["guest_count"]
        restaurant_id = get_restaurant_id_from_auth(self.request)
        settings = (
            RestaurantSettings.objects.filter(restaurant_id=restaurant_id).first()
            if restaurant_id is not None
            else None
        )
        currency = settings.currency if settings and settings.currency else "USD"
        with transaction.atomic():
            reservation = create_walk_in_reservation(
                table=table,
                guest_count=guest_count,
            )
            serializer.save(
                restaurant_id=restaurant_id,
                opened_by=self.request.user,
                reservation=reservation,
                currency=currency,
                opened_at=timezone.now(),
            )


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
