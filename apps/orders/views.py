from collections.abc import Sequence
from datetime import timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.authentication.models import RoleCode, User
from apps.authentication.permissions import IsFloor, IsKitchen, IsStaff
from apps.orders.selectors import compute_avg_prep_time, get_kitchen_order_items, get_kitchen_tickets
from apps.reservations.models import ReservationStatus
from apps.restaurants.models import RestaurantSettings
from common.api import (
    RestaurantScopedViewSetMixin,
    get_restaurant_id_from_auth,
    require_restaurant_id_from_auth,
)
from common.exceptions import TableOccupiedError
from common.hall_events import emit_hall_table_status_changed
from common.notification_events import emit_kitchen_ticket_injected, emit_order_item_status_changed

from .billing import close_visit_session, ensure_visit_session
from .models import Order, OrderItem, OrderItemStatus, Session, SessionStatus, Ticket, TicketStatus, VoidReason
from .serializers import (
    CreateOrderSerializer,
    OrderItemSerializer,
    OrderItemVoidRequestSerializer,
    OrderSerializer,
    SessionSerializer,
    TicketSerializer,
    TicketStatsSerializer,
    VoidReasonSerializer,
)
from .services import (
    create_order_with_items,
    create_walk_in_reservation,
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
        table = serializer.validated_data["table"]
        now = timezone.now()
        grace_minutes = max(int(getattr(settings, "SESSION_OVERDUE_AUTO_CLOSE_MINUTES", 20)), 0)
        occupancy_cutoff = now - timedelta(minutes=grace_minutes)
        if Session.objects.filter(
            table=table,
            status=SessionStatus.OPEN,
            reservation__status=ReservationStatus.ACTIVE,
            reservation__end_at__gt=occupancy_cutoff,
        ).exists():
            raise TableOccupiedError()
        guest_count = serializer.validated_data["guest_count"]
        with transaction.atomic():
            reservation = create_walk_in_reservation(table=table, guest_count=guest_count)
            # ensure_visit_session owns currency/opened_at resolution for every
            # open-table path (walk-in, scan, activate), so it stays in one place.
            # IsFloor guarantees an authenticated staff user here.
            serializer.instance = ensure_visit_session(reservation, opened_by=cast(User, self.request.user))
            restaurant_id = get_restaurant_id_from_auth(self.request)
            if restaurant_id is not None:

                def _on_commit() -> None:
                    emit_hall_table_status_changed(
                        restaurant_id,
                        table_id=str(table.public_id),
                        previous_status="free",
                        current_status="occupied",
                        session_id=str(serializer.instance.public_id),
                        actor=cast(User, self.request.user),
                    )

                transaction.on_commit(_on_commit)

    _ALLOWED_SESSION_PATCH_FIELDS = {"status", "guest_count"}

    def partial_update(self, request: Request, *args: object, **kwargs: object) -> Response:
        instance = self.get_object()

        new_status = request.data.get("status")
        if new_status and new_status != instance.status:
            instance = update_session_status(
                instance,
                new_status=new_status,
                actor=request.user,  # type: ignore[arg-type]
            )

        patch_data = {k: v for k, v in request.data.items() if k in self._ALLOWED_SESSION_PATCH_FIELDS}
        patch_data.pop("status", None)

        serializer = self.get_serializer(instance, data=patch_data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

    @extend_schema(
        summary="Close the check",
        description="End the visit: close the session, complete the reservation, and close any "
        "active cart so the table is freed. No payment step yet. Idempotent.",
        request=None,
        responses=SessionSerializer,
    )
    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        session = close_visit_session(session=self.get_object(), actor=cast(User, request.user))
        serializer = self.get_serializer(session)
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

    def get_permissions(self) -> Sequence[object]:  # type: ignore[override]
        if self.action == "create":
            return [IsFloor()]
        return super().get_permissions()

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        items_data = request.data.get("items")
        if items_data is not None:
            serializer = CreateOrderSerializer(
                data=request.data,
                context={"request": request},
            )
            serializer.is_valid(raise_exception=True)

            order = create_order_with_items(
                session=serializer.validated_data["session"],
                items=[
                    {
                        "menu_item": item["menu_item"],
                        "guest_slot": item["guest_slot"],
                        "quantity": item["quantity"],
                        "comment": item["comment"],
                    }
                    for item in serializer.validated_data["items"]
                ],
                actor=request.user,  # type: ignore[arg-type]
            )

            return Response(
                self.get_serializer(order).data,
                status=status.HTTP_201_CREATED,
            )

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
    permission_classes = [IsKitchen]
    queryset = Ticket.objects.select_related(
        "session__table",
        "order__created_by",
        "session",
        "restaurant",
    ).prefetch_related("items")
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

    def get_permissions(self) -> Sequence[object]:  # type: ignore[override]
        if self.action in {"list", "retrieve"}:
            return [IsStaff()]
        return super().get_permissions()

    def safely_get_queryset(self, qs: QuerySet[Ticket]) -> QuerySet[Ticket]:
        restaurant_id = get_restaurant_id_from_auth(self.request)
        if restaurant_id is None:
            return qs.none()
        qs = get_kitchen_tickets(restaurant_id)
        status_filter = self.request.query_params.get("status")
        if status_filter == TicketStatus.COMPLETED:
            settings = RestaurantSettings.objects.filter(restaurant_id=restaurant_id).first()
            tz = ZoneInfo(settings.timezone) if settings and settings.timezone else ZoneInfo("UTC")
            local_now = timezone.now().astimezone(tz)
            day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(ZoneInfo("UTC"))
            day_end = day_start + timedelta(days=1)
            qs = qs.filter(completed_at__gte=day_start, completed_at__lt=day_end)
        return qs

    def perform_update(self, serializer):  # type: ignore[no-untyped-def]
        if serializer.validated_data.get("status") == TicketStatus.COMPLETED:
            restaurant_id = serializer.instance.restaurant_id
            settings = RestaurantSettings.objects.filter(restaurant_id=restaurant_id).first()
            tz = ZoneInfo(settings.timezone) if settings and settings.timezone else ZoneInfo("UTC")
            now_local = timezone.now().astimezone(tz)
            serializer.save(completed_at=now_local)
        else:
            serializer.save()

    def perform_create(self, serializer):  # type: ignore[no-untyped-def]
        instance = serializer.save(restaurant_id=get_restaurant_id_from_auth(self.request))
        table_number = ""
        if instance.session_id:
            try:
                session_obj = Session.objects.get(pk=instance.session_id)
                table_number = session_obj.table.public_number
            except (Session.DoesNotExist, AttributeError):
                pass

        def _emit() -> None:
            emit_kitchen_ticket_injected(
                instance.restaurant_id,
                ticket_id=str(instance.public_id),
                table_number=table_number,
                items_count=instance.items.count(),
            )

        transaction.on_commit(_emit)

    @extend_schema(responses=TicketStatsSerializer)
    @action(
        detail=False,
        methods=["get"],
        url_path="stats",
        permission_classes=[IsStaff],
    )
    def stats(self, request: Request, *args: object, **kwargs: object) -> Response:
        restaurant_id = require_restaurant_id_from_auth(request)
        avg = compute_avg_prep_time(restaurant_id)
        serializer = TicketStatsSerializer(data={"avg_prep_time_seconds": avg})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


@extend_schema(tags=["Orders"])
class OrderItemViewSet(
    RestaurantScopedViewSetMixin[OrderItem],
    viewsets.ModelViewSet[OrderItem],
):
    permission_classes = [IsKitchen]
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = [
        "order",
        "order__public_id",
        "order__session__public_id",
        "ticket",
        "menu_item",
        "status",
        "voided_by",
        "void_reason",
        "is_wasted",
    ]
    ordering_fields = ["created_at", "updated_at", "guest_slot", "status", "voided_at"]

    def get_permissions(self) -> Sequence[object]:  # type: ignore[override]
        if self.action in {"list", "retrieve"}:
            return [IsStaff()]
        if self.action == "partial_update":
            return [IsStaff()]
        if self.action == "create":
            return [IsKitchen()]
        return super().get_permissions()

    def safely_get_queryset(self, qs: QuerySet[OrderItem]) -> QuerySet[OrderItem]:
        restaurant_id = get_restaurant_id_from_auth(self.request)
        if restaurant_id is None:
            return qs.none()
        return get_kitchen_order_items(restaurant_id)

    def perform_create(self, serializer):  # type: ignore[no-untyped-def]
        serializer.save(restaurant_id=get_restaurant_id_from_auth(self.request))

    def partial_update(self, request: Request, *args: object, **kwargs: object) -> Response:
        instance = self.get_object()
        previous_status = instance.status

        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data.get("status")
        if new_status is not None:
            self._enforce_status_permissions(request, new_status)
        serializer.save()

        instance.refresh_from_db()

        if previous_status != instance.status:
            table_number = ""
            try:
                order_session = instance.order.session
                table_number = order_session.table.public_number
            except AttributeError:
                pass

            def _emit() -> None:
                emit_order_item_status_changed(
                    instance.restaurant_id,
                    order_item_id=str(instance.public_id),
                    table_number=table_number,
                    menu_item_name=instance.menu_item.name if instance.menu_item else "",
                    status=instance.status,
                )

            transaction.on_commit(_emit)

        return Response(serializer.data)

    def _enforce_status_permissions(self, request: Request, status_value: str) -> None:
        role = getattr(request.user, "role", None)
        if role in {RoleCode.ADMIN, RoleCode.COOK}:
            return
        if role == RoleCode.WAITER and status_value == OrderItemStatus.SERVED:
            return
        raise PermissionDenied("Only kitchen staff can update this order item status.")

    @extend_schema(
        request=OrderItemVoidRequestSerializer,
        responses=OrderItemSerializer,
    )
    @action(detail=True, methods=["post"], url_path="void", permission_classes=[IsFloor])
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
