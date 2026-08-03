from typing import Any, cast

from django.db import IntegrityError
from django.db.models import QuerySet
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
    MonthSummaryQuerySerializer,
    ShiftListQuerySerializer,
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

    def get_permissions(self) -> list[Any]:
        if self.action in ("list", "retrieve", "month_summary"):
            return [IsStaff()]
        return [IsAdmin()]

    def get_serializer_class(self) -> type[Any]:
        if self.action in ("create", "partial_update", "update"):
            return ShiftWriteSerializer
        if self.action == "copy":
            return CopyShiftsSerializer
        return ShiftSerializer

    def safely_get_queryset(self, qs: QuerySet[Shift]) -> QuerySet[Shift]:
        return qs.select_related("employee")

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        write_serializer = self.get_serializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        self.perform_create(cast(ShiftWriteSerializer, write_serializer))
        read_serializer = ShiftSerializer(
            write_serializer.instance,
            context=self.get_serializer_context(),
        )
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        write_serializer = self.get_serializer(instance, data=request.data, partial=partial)
        write_serializer.is_valid(raise_exception=True)
        self.perform_update(cast(ShiftWriteSerializer, write_serializer))
        read_serializer = ShiftSerializer(instance, context=self.get_serializer_context())
        return Response(read_serializer.data)

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        restaurant_id = get_restaurant_id_from_auth(request)
        if restaurant_id is None:
            return Response([])

        query_serializer = ShiftListQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        qs = list_shifts(
            restaurant_id,
            date=params.get("date"),
            date_from=params.get("date_from"),
            date_to=params.get("date_to"),
            employee_id=str(params["employee_id"]) if params.get("employee_id") else None,
        )
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer: ShiftWriteSerializer) -> None:  # type: ignore[override]
        restaurant_id = get_restaurant_id_from_auth(self.request)
        if restaurant_id is None:
            from rest_framework.exceptions import ValidationError as DRFValidationError
            raise DRFValidationError("Restaurant not found.")
        try:
            shift = create_shift(
                restaurant_id=restaurant_id,
                **serializer.validated_data,
            )
        except ValueError as e:
            from rest_framework.exceptions import ValidationError as DRFValidationError
            raise DRFValidationError(str(e)) from e
        serializer.instance = shift

    def perform_update(self, serializer: ShiftWriteSerializer) -> None:  # type: ignore[override]
        shift = serializer.instance
        if shift is None:
            from rest_framework.exceptions import ValidationError as DRFValidationError
            raise DRFValidationError("Shift instance is required for update.")
        try:
            update_shift(shift, **serializer.validated_data)
        except ValueError as e:
            from rest_framework.exceptions import ValidationError as DRFValidationError
            raise DRFValidationError(str(e)) from e
        serializer.instance = shift

    def perform_destroy(self, instance: Shift) -> None:
        delete_shift(instance)

    @action(detail=False, methods=["post"])
    def copy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        restaurant_id = get_restaurant_id_from_auth(request)
        if restaurant_id is None:
            return Response(
                {"detail": "Restaurant not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CopyShiftsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        employee_ids = serializer.validated_data.get("employee_ids")
        try:
            total = copy_shifts(
                restaurant_id=restaurant_id,
                source_date=serializer.validated_data["source_date"],
                target_dates=serializer.validated_data["target_dates"],
                employee_ids=[str(e) for e in employee_ids] if employee_ids else None,
            )
        except IntegrityError:
            return Response(
                {"detail": "Some shifts already exist on target dates."},
                status=status.HTTP_409_CONFLICT,
            )

        return Response({"copied": total}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def month_summary(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        restaurant_id = get_restaurant_id_from_auth(request)
        if restaurant_id is None:
            return Response({"total_hours": 0.0, "shifts": []})

        query_serializer = MonthSummaryQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        shifts = get_month_summary(
            restaurant_id,
            year=params["year"],
            month=params["month"],
            employee_id=str(params["employee_id"]) if params.get("employee_id") else None,
        )

        total_hours = sum(s["duration_hours"] for s in shifts)
        return Response({
            "total_hours": round(total_hours, 2),
            "shifts": shifts,
        })
