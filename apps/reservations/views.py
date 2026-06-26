from collections.abc import Sequence
from datetime import date as date_type
from datetime import datetime, timedelta
from datetime import time as time_type
from typing import cast
from zoneinfo import ZoneInfo

from django.db.models import QuerySet
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.authentication.models import RoleCode, User
from apps.orders.models import Session
from apps.restaurants.models import Restaurant, RestaurantSettings, Table
from common.api import PublicLookupMixin, PublicRestaurantQueryMixin, get_restaurant_id_from_auth

from .models import Reservation, ReservationStatus
from .permissions import CanManageReservations
from .selectors import get_customer_global_reservations, get_customer_reservations
from .serializers import ReservationSerializer
from .services import (
    activate_reservation,
    cancel_reservation,
    close_session,
    create_reservation,
    create_staff_reservation,
    move_session_to_table,
    reschedule_reservation,
    update_reservation_status,
)


def _parse_time(value: str) -> time_type:
    parts = value.split(":")
    return time_type(hour=int(parts[0]), minute=int(parts[1]))


def _parse_non_negative_int(value: str | None, field_name: str) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        raise ValidationError(f"{field_name} must be a non-negative integer.") from None
    if parsed < 0:
        raise ValidationError(f"{field_name} must be a non-negative integer.")
    return parsed


@extend_schema(tags=["Reservations"])
class ReservationViewSet(
    PublicLookupMixin,
    PublicRestaurantQueryMixin,
    viewsets.ModelViewSet[Reservation],
):
    queryset = Reservation.objects.all()
    serializer_class = ReservationSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["customer", "table", "status"]
    ordering_fields = ["created_at", "updated_at", "start_at", "end_at", "guest_count"]

    def get_permissions(self) -> Sequence[BasePermission]:
        if self.action == "available_slots":
            return [AllowAny()]
        return [IsAuthenticated(), CanManageReservations()]

    def get_queryset(self) -> QuerySet[Reservation]:
        qs = super().get_queryset()
        role = getattr(self.request.user, "role", None)
        if role and role in (RoleCode.ADMIN, RoleCode.WAITER):
            restaurant_id = get_restaurant_id_from_auth(self.request)
            if restaurant_id is not None:
                return qs.filter(restaurant_id=restaurant_id)
            return qs.none()
        return qs.filter(customer_id=self.request.user.pk)

    def create(self, request: Request, *args: object) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        restaurant_id = get_restaurant_id_from_auth(request)

        if restaurant_id is None:
            table = serializer.validated_data["table"]
            restaurant_id = table.restaurant_id

        user = cast(User, request.user)
        guest_name = request.data.get("guest_name")

        if guest_name and getattr(user, "role", None) in (RoleCode.ADMIN, RoleCode.WAITER):
            reservation = create_staff_reservation(
                restaurant_id=restaurant_id,
                table_id=str(serializer.validated_data["table"].public_id),
                guest_count=serializer.validated_data["guest_count"],
                start_at=serializer.validated_data["start_at"],
                end_at=serializer.validated_data["end_at"],
                guest_name=guest_name,
                guest_phone=request.data.get("guest_phone", ""),
                notes=serializer.validated_data.get("notes"),
                actor=user,
            )
        else:
            reservation = create_reservation(
                restaurant_id=restaurant_id,
                customer_id=user.pk,
                table_id=str(serializer.validated_data["table"].public_id),
                guest_count=serializer.validated_data["guest_count"],
                start_at=serializer.validated_data["start_at"],
                end_at=serializer.validated_data["end_at"],
                notes=serializer.validated_data.get("notes"),
                actor=user,
            )

        result_serializer = self.get_serializer(reservation)
        return Response(result_serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, *args: object, **kwargs: object) -> Response:
        instance = self.get_object()
        if getattr(request.user, "role", None) == RoleCode.CUSTOMER:
            if instance.customer_id != request.user.pk:
                raise PermissionDenied("You can only modify your own reservations.")
            if instance.status == ReservationStatus.ACTIVE:
                raise PermissionDenied("This reservation is already active and can no longer be changed.")
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        status_val = serializer.validated_data.pop("status", None)
        if status_val is not None:
            if status_val == ReservationStatus.CANCELLED:
                reservation = cancel_reservation(reservation=instance)
            else:
                reservation = update_reservation_status(
                    instance,
                    new_status=status_val,
                    actor=request.user,  # type: ignore[arg-type]
                )
            result_serializer = self.get_serializer(reservation)
            return Response(result_serializer.data)

        reservation = reschedule_reservation(
            reservation=instance,
            validated_data=serializer.validated_data,
        )

        result_serializer = self.get_serializer(reservation)
        return Response(result_serializer.data)

    @extend_schema(
        summary="Activate a reservation",
        description="Flips a pending reservation to active without a QR scan. "
        "Allowed for restaurant staff or the owning customer. Idempotent if already active.",
        request=None,
        responses={200: ReservationSerializer},
    )
    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request: Request, *args: object, **kwargs: object) -> Response:
        reservation = self.get_object()
        is_staff = getattr(request.user, "role", None) in (RoleCode.ADMIN, RoleCode.WAITER)
        result = activate_reservation(
            reservation=reservation,
            opened_by=request.user,
            enforce_window=not is_staff,
        )
        serializer = self.get_serializer(result)
        return Response(serializer.data)

    @extend_schema(
        summary="Available time slots for a table",
        description="Returns available 30-min time slots for a table. "
        "If date is provided, returns slots for that date only. "
        "Otherwise returns slots for the next 14 days.",
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="available-slots",
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def available_slots(self, request: Request) -> Response:
        table_id = request.query_params.get("table")
        date_str = request.query_params.get("date")
        exclude_ids = request.query_params.getlist("exclude")

        if not table_id:
            raise ValidationError("table query parameter is required.")

        try:
            table = Table.objects.get(public_id=table_id, active=True)
        except Table.DoesNotExist:
            raise ValidationError("Table not found.") from None

        settings = RestaurantSettings.objects.filter(restaurant_id=table.restaurant_id).first()
        working_hours = settings.working_hours if settings else {}
        tz = ZoneInfo(settings.timezone) if settings else ZoneInfo("UTC")

        today_local = timezone.now().astimezone(tz).date()

        qs = Reservation.objects.filter(
            table=table,
            status__in=[ReservationStatus.PENDING, ReservationStatus.ACTIVE],
        )
        if exclude_ids:
            qs = qs.exclude(public_id__in=exclude_ids)
        reservations = list(qs.values("start_at", "end_at"))

        now_utc = timezone.now()

        # working_hours uses 3-letter keys (mon–sun); index by weekday() (0=Mon)
        # to stay locale-independent rather than relying on strftime names.
        weekday_keys = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

        def day_slots(d: date_type) -> list[str]:
            day_name = weekday_keys[d.weekday()]
            day_config = working_hours.get(day_name)
            if not day_config:
                return []

            open_t = _parse_time(day_config["open"])
            close_t = _parse_time(day_config["close"])

            open_minutes = open_t.hour * 60 + open_t.minute
            close_minutes = close_t.hour * 60 + close_t.minute
            overnight = close_minutes <= open_minutes
            end_base = close_minutes + (24 * 60 if overnight else 0)

            slots: list[str] = []
            minute = open_minutes
            while minute < end_base:
                h = (minute // 60) % 24
                m = minute % 60
                slot_start_str = f"{h:02d}:{m:02d}"

                slot_date = d + timedelta(days=1) if minute >= 24 * 60 else d
                slot_local = datetime(slot_date.year, slot_date.month, slot_date.day, h, m, tzinfo=tz)
                slot_utc = slot_local.astimezone(ZoneInfo("UTC"))
                slot_end_utc = slot_utc + timedelta(minutes=30)

                if d == today_local and slot_utc <= now_utc:
                    minute += 30
                    continue

                overlaps = any(slot_utc < r["end_at"] and slot_end_utc > r["start_at"] for r in reservations)
                if not overlaps:
                    slots.append(slot_start_str)

                minute += 30

            return slots

        result: dict[str, list[str]] = {}
        if date_str:
            try:
                d = date_type.fromisoformat(date_str)
            except ValueError:
                raise ValidationError("Invalid date format. Use YYYY-MM-DD.") from None
            result[date_str] = day_slots(d)
        else:
            for i in range(14):
                d = today_local + timedelta(days=i)
                result[d.isoformat()] = day_slots(d)

        return Response(result)

    @extend_schema(responses=ReservationSerializer(many=True))
    @action(detail=False, methods=["get"], url_path="my")
    def my(self, request: Request) -> Response:
        limit = _parse_non_negative_int(request.query_params.get("limit"), "limit")
        offset = _parse_non_negative_int(request.query_params.get("offset"), "offset") or 0
        restaurant_id = get_restaurant_id_from_auth(request)
        if restaurant_id is None:
            public_id = request.query_params.get(self.restaurant_query_param)
            if public_id:
                try:
                    restaurant = Restaurant.objects.get(public_id=public_id)
                    restaurant_id = restaurant.id
                except Restaurant.DoesNotExist:
                    raise ValidationError("Restaurant not found.") from None
            else:
                reservations = get_customer_global_reservations(request.user.pk)  # type: ignore[arg-type]
                if limit is not None:
                    reservations = reservations[offset : offset + limit]
                elif offset:
                    reservations = reservations[offset:]
                serializer = self.get_serializer(reservations, many=True)
                return Response(serializer.data)
        reservations = get_customer_reservations(request.user.pk, restaurant_id=restaurant_id)  # type: ignore[arg-type]
        if limit is not None:
            reservations = reservations[offset : offset + limit]
        elif offset:
            reservations = reservations[offset:]
        serializer = self.get_serializer(reservations, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Move session to another table",
        description=(
            "Moves an active session to a new table. "
            "Cancels the old reservation and creates a new one. "
            "Pending items travel with the session."
        ),
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "table_id": {"type": "string", "format": "uuid"},
                },
                "required": ["table_id"],
            }
        },
    )
    @action(detail=True, methods=["post"], url_path="move-table")
    def move_table(self, request: Request, public_id: str | None = None) -> Response:
        reservation = self.get_object()
        user = cast(User, request.user)

        if getattr(user, "role", None) not in (RoleCode.ADMIN, RoleCode.WAITER):
            raise PermissionDenied("Only staff can move tables.")

        try:
            session = Session.objects.get(reservation=reservation, status="open")
        except Session.DoesNotExist:
            raise ValidationError("No active session for this reservation.") from None

        table_id = request.data.get("table_id")
        if not table_id:
            raise ValidationError("table_id is required.")

        move_session_to_table(session, new_table_id=table_id, actor=user)

        return Response({"detail": "Session moved successfully."})

    @extend_schema(
        summary="Close check (session)",
        description="Closes the session. All items must be served or voided.",
    )
    @action(detail=True, methods=["post"], url_path="close-check")
    def close_check(self, request: Request, public_id: str | None = None) -> Response:
        reservation = self.get_object()
        user = cast(User, request.user)

        if getattr(user, "role", None) not in (RoleCode.ADMIN, RoleCode.WAITER):
            raise PermissionDenied("Only staff can close checks.")

        try:
            session = Session.objects.get(reservation=reservation, status="open")
        except Session.DoesNotExist:
            raise ValidationError("No active session for this reservation.") from None

        close_session(session, actor=user)

        return Response({"detail": "Check closed successfully."})
