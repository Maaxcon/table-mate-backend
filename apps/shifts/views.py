from datetime import date as date_type

from django.db import IntegrityError
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.authentication.permissions import IsAdmin, IsStaff
from common.api import RestaurantScopedViewSetMixin, get_restaurant_id_from_auth

from .models import Shift
from .selectors import get_month_summary, list_shifts
from .serializers import (
    CopyShiftsSerializer,
    ShiftSerializer,
    ShiftWriteSerializer,
)
from .services import copy_shifts, create_shift, delete_shift, update_shift


class ShiftViewSet(
    RestaurantScopedViewSetMixin[Shift],
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet[Shift],
):
    queryset = Shift.objects.all()
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve", "month_summary"):
            return [IsStaff()]
        return [IsAdmin()]

    def get_serializer_class(self):
        if self.action in ("create", "partial_update", "update"):
            return ShiftWriteSerializer
        if self.action == "copy":
            return CopyShiftsSerializer
        return ShiftSerializer

    def safely_get_queryset(self, qs):
        return qs.select_related("employee")

    def list(self, request: Request, *args, **kwargs):
        restaurant_id = get_restaurant_id_from_auth(request)
        if restaurant_id is None:
            return Response([])

        params = request.query_params
        date_param = params.get("date")
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        employee_id = params.get("employee_id")

        date_obj: date_type | None = None
        if date_param:
            try:
                date_obj = date_type.fromisoformat(date_param)
            except (ValueError, TypeError):
                pass

        date_from_obj: date_type | None = None
        if date_from:
            try:
                date_from_obj = date_type.fromisoformat(date_from)
            except (ValueError, TypeError):
                pass

        date_to_obj: date_type | None = None
        if date_to:
            try:
                date_to_obj = date_type.fromisoformat(date_to)
            except (ValueError, TypeError):
                pass

        qs = list_shifts(
            restaurant_id,
            date=date_obj,
            date_from=date_from_obj,
            date_to=date_to_obj,
            employee_id=employee_id,
        )
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        restaurant_id = get_restaurant_id_from_auth(self.request)
        shift = create_shift(
            restaurant_id=restaurant_id,
            **serializer.validated_data,
        )
        serializer.instance = shift

    def perform_update(self, serializer):
        shift = self.get_object()
        update_shift(shift, **serializer.validated_data)
        serializer.instance = shift

    def perform_destroy(self, instance):
        delete_shift(instance)

    @action(detail=False, methods=["post"])
    def copy(self, request: Request, *args, **kwargs):
        restaurant_id = get_restaurant_id_from_auth(request)
        if restaurant_id is None:
            return Response(
                {"detail": "Restaurant not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CopyShiftsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            total = copy_shifts(
                restaurant_id=restaurant_id,
                source_date=serializer.validated_data["source_date"],
                target_dates=serializer.validated_data["target_dates"],
                employee_ids=serializer.validated_data.get("employee_ids"),
            )
        except IntegrityError:
            return Response(
                {"detail": "Some shifts already exist on target dates."},
                status=status.HTTP_409_CONFLICT,
            )

        return Response({"copied": total}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def month_summary(self, request: Request, *args, **kwargs):
        restaurant_id = get_restaurant_id_from_auth(request)
        if restaurant_id is None:
            return Response({"total_hours": 0.0, "shifts": []})

        year = request.query_params.get("year")
        month = request.query_params.get("month")
        employee_id = request.query_params.get("employee_id")

        if not year or not month:
            return Response(
                {"detail": "year and month query params are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            year_int = int(year)
            month_int = int(month)
        except (ValueError, TypeError):
            return Response(
                {"detail": "Invalid year or month."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        shifts = get_month_summary(
            restaurant_id,
            year=year_int,
            month=month_int,
            employee_id=employee_id,
        )

        total_hours = sum(s["duration_hours"] for s in shifts)
        return Response({
            "total_hours": round(total_hours, 2),
            "shifts": shifts,
        })
