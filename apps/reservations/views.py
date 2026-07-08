import uuid
from collections.abc import Sequence
from datetime import date as date_type
from datetime import datetime, timedelta
from datetime import time as time_type
from typing import cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import QuerySet
from django.utils import timezone
from drf_spectacular.plumbing import build_array_type, build_basic_type, build_object_type
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.authentication.models import RoleCode, User
from apps.orders.models import Session
from apps.restaurants.models import Restaurant, RestaurantSettings, Table
from apps.restaurants.selectors import _DAY_KEYS
from common.api import PublicLookupMixin, PublicRestaurantQueryMixin, get_restaurant_id_from_auth
from common.channels import resolve_restaurant_pk_sync

from .filters import ReservationFilter
from .models import Reservation, ReservationStatus
from .permissions import CanManageReservations
from .selectors import (
    PAST_STATUSES,
    get_customer_global_reservations,
    get_customer_reservations,
    get_session_grace_cutoffs,
    get_unavailable_table_ids,
)
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


def _day_window(day_config: object) -> tuple[int, int] | None:
    """Open minute and (overnight-aware) close minute for a working-hours day, or
    None if the day is closed or its stored config is malformed (missing or
    non-HH:MM open/close). Keeps a bad stored config from raising a 500."""
    if not isinstance(day_config, dict):
        return None
    open_str = day_config.get("open")
    close_str = day_config.get("close")
    if not isinstance(open_str, str) or not isinstance(close_str, str):
        return None
    try:
        open_t = _parse_time(open_str)
        close_t = _parse_time(close_str)
    except (ValueError, IndexError):
        return None
    open_minutes = open_t.hour * 60 + open_t.minute
    close_minutes = close_t.hour * 60 + close_t.minute
    overnight = close_minutes <= open_minutes
    end_base = close_minutes + (24 * 60 if overnight else 0)
    return open_minutes, end_base


def _safe_zoneinfo(name: object) -> ZoneInfo:
    """A restaurant's stored timezone as ZoneInfo, falling back to UTC for a blank
    or misconfigured value — a bad setting shouldn't 500 the public endpoints."""
    if isinstance(name, str) and name:
        try:
            return ZoneInfo(name)
        except (ValueError, ZoneInfoNotFoundError):
            pass
    return ZoneInfo("UTC")


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
    filterset_class = ReservationFilter
    ordering_fields = ["created_at", "updated_at", "start_at", "end_at", "guest_count"]

    def get_permissions(self) -> Sequence[BasePermission]:
        if self.action in ("available_slots", "availability"):
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
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        status_val = serializer.validated_data.pop("status", None)
        if status_val is not None:
            if status_val == ReservationStatus.CANCELLED:
                if (
                    getattr(request.user, "role", None) == RoleCode.CUSTOMER
                    and instance.status == ReservationStatus.ACTIVE
                ):
                    raise PermissionDenied("You cannot cancel an active reservation.")
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
        responses=OpenApiResponse(
            response=build_object_type(
                additionalProperties=build_array_type(build_basic_type(OpenApiTypes.STR)),
                description="date (YYYY-MM-DD) -> list of bookable HH:MM slot start times",
            ),
        ),
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="available-slots",
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
        tz = _safe_zoneinfo(settings.timezone if settings else None)

        today_local = timezone.now().astimezone(tz).date()

        qs = Reservation.objects.filter(
            table=table,
            status__in=[ReservationStatus.PENDING, ReservationStatus.ACTIVE],
        )
        if exclude_ids:
            qs = qs.exclude(public_id__in=exclude_ids)
        reservations = list(qs.values("start_at", "end_at"))

        now_utc = timezone.now()

        # A currently open session may still occupy the table when a near-term
        # slot starts (overstaying guests, or seated after the booked start).
        # Same fixed grace period the availability action and the
        # booking-conflict check use, so a slot listed here doesn't 409 when
        # actually booked.
        session_cutoff = get_session_grace_cutoffs(table.restaurant_id, [table.pk], now_utc).get(
            table.pk
        )

        def day_slots(d: date_type) -> list[str]:
            day_name = _DAY_KEYS[d.weekday()]
            window = _day_window(working_hours.get(day_name))
            if not window:
                return []

            open_minutes, end_base = window

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
                blocked_by_session = session_cutoff is not None and slot_utc < session_cutoff
                if not overlaps and not blocked_by_session:
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

    @extend_schema(
        summary="Per-table availability for one slot",
        description="Given restaurant + date + time (+ optional duration in minutes, "
        "default 120), returns each active table's availability for that slot as "
        "{ availability: { '<table_public_id>': true|false } }. A table is free when "
        "the slot is within working hours, in the future, and has no overlapping "
        "pending/active reservation. Powers the time-aware floor plan.",
        responses=inline_serializer(
            name="TableAvailabilityResponse",
            fields={
                "availability": drf_serializers.DictField(
                    child=drf_serializers.BooleanField(),
                    help_text="table public_id -> is it free for the requested slot",
                ),
            },
        ),
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="availability",
        authentication_classes=[],
    )
    def availability(self, request: Request) -> Response:
        restaurant_id = request.query_params.get("restaurant")
        date_str = request.query_params.get("date")
        time_str = request.query_params.get("time")
        duration = _parse_non_negative_int(request.query_params.get("duration"), "duration") or 120
        duration = max(duration, 30)

        if not restaurant_id:
            raise ValidationError("restaurant query parameter is required.")
        if not date_str or not time_str:
            raise ValidationError("date and time query parameters are required.")

        try:
            d = date_type.fromisoformat(date_str)
        except ValueError:
            raise ValidationError("Invalid date format. Use YYYY-MM-DD.") from None
        try:
            t = _parse_time(time_str)
        except (ValueError, IndexError):
            raise ValidationError("Invalid time format. Use HH:MM.") from None

        # Validate + resolve the public_id to an integer pk once (a raw UUID cast on
        # a bad id would 500). resolve_restaurant_pk_sync returns None for a
        # malformed UUID or an unknown restaurant: a bad id is a client error, a
        # valid-but-missing one simply has no floor to report. This view is a
        # plain sync DRF view, so it uses the sync resolver directly — the async
        # resolve_restaurant_pk (database_sync_to_async-wrapped, for WebSocket
        # consumers) would return an unawaited coroutine here instead of an int.
        restaurant_pk = resolve_restaurant_pk_sync(restaurant_id)
        if restaurant_pk is None:
            try:
                uuid.UUID(str(restaurant_id))
            except (ValueError, AttributeError, TypeError):
                raise ValidationError("Invalid restaurant id.") from None
            return Response({"availability": {}})

        settings = RestaurantSettings.objects.filter(restaurant_id=restaurant_pk).first()
        working_hours = settings.working_hours if settings else {}
        tz = _safe_zoneinfo(settings.timezone if settings else None)

        tables = list(Table.objects.filter(restaurant_id=restaurant_pk, active=True))

        now_utc = timezone.now()

        # The slot must start within working hours and leave at least a minimum
        # bookable window (30 min) before close. The booking window is capped to
        # closing time, so a 2h default near closing still counts as available for
        # however long remains (e.g. 90 min until a 22:00 close). Weekday keys are
        # locale-independent (0 = Monday).
        day_config = working_hours.get(_DAY_KEYS[d.weekday()]) if working_hours else None
        window = _day_window(day_config)
        within_hours = False
        effective_duration = duration
        # An after-midnight slot on an overnight day (e.g. 01:00 when the venue opens
        # 18:00) belongs to the next calendar day and sits on the extended timeline
        # (24:00 = 1440+) — exactly how day_slots lists it. Resolve it the same way,
        # or the slot reads as before opening and every table is reported as taken.
        slot_date = d
        if window:
            open_minutes, end_base = window
            slot_minutes = t.hour * 60 + t.minute
            overnight = end_base > 24 * 60
            if overnight and slot_minutes < open_minutes:
                slot_minutes += 24 * 60
                slot_date = d + timedelta(days=1)
            until_close = end_base - slot_minutes
            within_hours = slot_minutes >= open_minutes and until_close >= 30
            effective_duration = min(duration, until_close)

        slot_local = datetime(slot_date.year, slot_date.month, slot_date.day, t.hour, t.minute, tzinfo=tz)
        slot_start = slot_local.astimezone(ZoneInfo("UTC"))
        slot_end = slot_start + timedelta(minutes=effective_duration)

        result: dict[str, bool] = {}

        if not (within_hours and slot_start > now_utc):
            for table in tables:
                result[str(table.public_id)] = False
            return Response({"availability": result})

        # Same selector the booking-conflict check and the floor editor use, so
        # a table marked free here can't 409 when the guest actually books it.
        unavailable = get_unavailable_table_ids(
            restaurant_id=restaurant_pk,
            start_at=slot_start,
            end_at=slot_end,
            table_ids=[t.pk for t in tables],
            now=now_utc,
        )
        for table in tables:
            result[str(table.public_id)] = table.pk not in unavailable

        return Response({"availability": result})

    @extend_schema(responses=ReservationSerializer(many=True))
    @action(detail=False, methods=["get"], url_path="my")
    def my(self, request: Request) -> Response:
        limit = _parse_non_negative_int(request.query_params.get("limit"), "limit")
        offset = _parse_non_negative_int(request.query_params.get("offset"), "offset") or 0
        # ?status=past returns the guest's history (completed/cancelled), newest
        # first; the default keeps the active pending/active list.
        past = request.query_params.get("status") == "past"
        statuses = PAST_STATUSES if past else None

        def paginate(qs: QuerySet[Reservation]) -> QuerySet[Reservation]:
            if past:
                qs = qs.order_by("-start_at")
            if limit is not None:
                return qs[offset : offset + limit]
            if offset:
                return qs[offset:]
            return qs

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
                reservations = get_customer_global_reservations(request.user.pk, statuses=statuses)  # type: ignore[arg-type]
                serializer = self.get_serializer(paginate(reservations), many=True)
                return Response(serializer.data)
        reservations = get_customer_reservations(
            request.user.pk,  # type: ignore[arg-type]
            restaurant_id=restaurant_id,
            statuses=statuses,
        )
        serializer = self.get_serializer(paginate(reservations), many=True)
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
