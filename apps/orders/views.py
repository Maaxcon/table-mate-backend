from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.authentication.permissions import IsFloor, IsStaff
from common.api import RestaurantScopedViewSetMixin, get_restaurant_id_from_auth

from .models import Order, OrderItem, Session, Ticket, VoidReason
from .serializers import (
    OrderItemSerializer,
    OrderSerializer,
    SessionSerializer,
    TicketSerializer,
    VoidReasonSerializer,
)
from .services import (
    create_order_with_items,
    open_session,
    update_session_status,
    void_order_item,
)


@extend_schema(tags=["Orders"])
class VoidReasonViewSet(viewsets.ReadOnlyModelViewSet[VoidReason]):
    permission_classes = [IsAuthenticated]
    queryset = VoidReason.objects.all()
    serializer_class = VoidReasonSerializer
    pagination_class = None


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
        restaurant_id = get_restaurant_id_from_auth(self.request)
        if not self.request.user.is_authenticated or restaurant_id is None:
            raise serializers.ValidationError("Authentication required")
        instance = open_session(
            restaurant_id=restaurant_id,
            table=serializer.validated_data["table"],
            guest_count=serializer.validated_data["guest_count"],
            opened_by=self.request.user,
            currency=serializer.validated_data["currency"],
            opened_at=serializer.validated_data["opened_at"],
            actor=self.request.user,
        )
        serializer.instance = instance

    def partial_update(self, request: Request, *args: object, **kwargs: object) -> Response:
        instance = self.get_object()

        new_status = request.data.get("status")
        if new_status and new_status != instance.status:
            instance = update_session_status(
                instance,
                new_status=new_status,
                actor=request.user,  # type: ignore[arg-type]
            )

        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

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

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        items_data = request.data.get("items")
        if items_data is not None:
            from apps.menu.models import MenuItem

            restaurant_id = get_restaurant_id_from_auth(request)
            if restaurant_id is None:
                return Response(
                    {"detail": "Restaurant ID not found in authentication."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            session_id = request.data.get("session")

            if not session_id:
                return Response(
                    {"detail": "session is required when items are provided."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            from .models import Session as SessionModel

            try:
                session = SessionModel.objects.get(
                    public_id=session_id,
                    restaurant_id=restaurant_id,
                )
            except SessionModel.DoesNotExist:
                return Response(
                    {"detail": "Session not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            items = []
            for item_data in items_data:
                menu_item_id = item_data.get("menu_item")
                if not menu_item_id:
                    return Response(
                        {"detail": "Each item must have a menu_item."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                try:
                    menu_item = MenuItem.objects.get(
                        public_id=menu_item_id,
                        restaurant_id=restaurant_id,
                    )
                except MenuItem.DoesNotExist:
                    return Response(
                        {"detail": f"Menu item {menu_item_id} not found."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                items.append({
                    "menu_item": menu_item,
                    "guest_slot": item_data.get("guest_slot", 1),
                    "quantity": item_data.get("quantity", 1),
                    "comment": item_data.get("comment"),
                })

            order = create_order_with_items(
                session=session,
                items=items,
                actor=request.user,  # type: ignore[arg-type]
            )

            serializer = self.get_serializer(order)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return super().create(request, *args, **kwargs)

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

    @extend_schema(
        request=serializers.Serializer({
            "void_reason": serializers.CharField(),
            "note": serializers.CharField(required=False, allow_null=True, default=None),
        }),
        responses=OrderItemSerializer,
    )
    @action(detail=True, methods=["post"], url_path="void")
    def void(self, request: Request, *args: object, **kwargs: object) -> Response:
        item = self.get_object()
        void_reason = request.data.get("void_reason")
        note = request.data.get("note")

        if not void_reason:
            return Response(
                {"detail": "void_reason is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = void_order_item(
                item,
                actor=request.user,  # type: ignore[arg-type]
                void_reason_code=void_reason,
                note=note,
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(result)
        return Response(serializer.data)
