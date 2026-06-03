from collections.abc import Sequence

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.restaurants.models import Restaurant
from common.api import PublicLookupMixin, PublicRestaurantQueryMixin, get_restaurant_id_from_auth

from .models import Reservation, ReservationStatus
from .permissions import CanManageReservations
from .selectors import get_customer_global_reservations, get_customer_reservations
from .serializers import ReservationSerializer
from .services import create_reservation, reschedule_reservation


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
        return [IsAuthenticated(), CanManageReservations()]

    def get_queryset(self) -> QuerySet[Reservation]:
        qs = super().get_queryset()
        role = getattr(self.request.user, "role", None)
        if role and role in ("admin", "waiter"):
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

        reservation = create_reservation(
            restaurant_id=restaurant_id,
            customer_id=request.user.pk,  # type: ignore[arg-type]
            table_id=str(serializer.validated_data["table"].public_id),
            guest_count=serializer.validated_data["guest_count"],
            start_at=serializer.validated_data["start_at"],
            end_at=serializer.validated_data["end_at"],
            notes=serializer.validated_data.get("notes"),
        )

        result_serializer = self.get_serializer(reservation)
        return Response(result_serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, *args: object) -> Response:
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        status_val = serializer.validated_data.pop("status", None)
        if status_val == ReservationStatus.CANCELLED:
            instance.status = ReservationStatus.CANCELLED
            instance.save(update_fields=["status"])
            result_serializer = self.get_serializer(instance)
            return Response(result_serializer.data)

        reservation = reschedule_reservation(
            reservation=instance,
            validated_data=serializer.validated_data,
        )

        result_serializer = self.get_serializer(reservation)
        return Response(result_serializer.data)

    @extend_schema(responses=ReservationSerializer(many=True))
    @action(detail=False, methods=["get"], url_path="my")
    def my(self, request: Request) -> Response:
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
                serializer = self.get_serializer(reservations, many=True)
                return Response(serializer.data)
        reservations = get_customer_reservations(request.user.pk, restaurant_id=restaurant_id)  # type: ignore[arg-type]
        serializer = self.get_serializer(reservations, many=True)
        return Response(serializer.data)
