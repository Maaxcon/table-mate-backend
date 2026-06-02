from typing import Any, cast

from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.models import User
from apps.authentication.permissions import IsFloor, IsStaff
from common.api import RestaurantScopedViewSetMixin, get_restaurant_id_from_auth
from common.idempotency import IdempotencyKeyMixin

from .models import Order, OrderItem, Session, Ticket
from .serializers import (
    CreateOrderFromCartSerializer,
    OrderItemSerializer,
    OrderSerializer,
    SessionSerializer,
    TicketSerializer,
)
from .services import submit_order


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


@extend_schema(tags=["Orders"])
class OrderSubmitView(IdempotencyKeyMixin, APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CreateOrderFromCartSerializer

    @extend_schema(
        request=CreateOrderFromCartSerializer,
        responses={201: OrderSerializer},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        idempotency_key = self.validate_idempotency_key(request)
        if idempotency_key is not None:
            cached = self.get_cached_response(idempotency_key, request)
            if cached is not None:
                return cached

        restaurant_id = get_restaurant_id_from_auth(request)
        if restaurant_id is None:
            return Response(
                {"detail": "Restaurant context required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CreateOrderFromCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = cast(User, request.user)
        items_data = [
            {
                "menu_item_id": entry["menu_item_id"],
                "quantity": entry["quantity"],
                "guest_slot": entry["guest_slot"],
                "comment": entry.get("comment", ""),
            }
            for entry in serializer.validated_data["items"]
        ]

        order = submit_order(
            restaurant_id=restaurant_id,
            table_id=str(serializer.validated_data["table_id"]),
            items_data=items_data,
            user=user,
            notes=serializer.validated_data.get("notes"),
        )

        result = OrderSerializer(order, context={"request": request})
        response = Response(result.data, status=status.HTTP_201_CREATED)

        if idempotency_key is not None:
            self.cache_response(idempotency_key, response, request)

        return response
