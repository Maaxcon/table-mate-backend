from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from common.api import RestaurantScopedViewSetMixin
from common.permissions import HasAnyRole

from .models import Reservation
from .selectors import get_customer_reservations
from .serializers import ReservationSerializer
from .services import create_reservation


@extend_schema(tags=["Reservations"])
class ReservationViewSet(
    RestaurantScopedViewSetMixin[Reservation],
    viewsets.ModelViewSet[Reservation],
):
    queryset = Reservation.objects.all()
    serializer_class = ReservationSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["customer", "table", "status"]
    ordering_fields = ["created_at", "updated_at", "start_at", "end_at", "guest_count"]

    def get_permissions(self) -> list[BasePermission]:
        if self.action in ("create", "my"):
            return [IsAuthenticated(), HasAnyRole.with_roles("customer")]
        return [IsAuthenticated()]

    def create(self, request: Request, *args: object) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        auth = getattr(request, "auth", None)
        restaurant_id = None
        if auth is not None and hasattr(auth, "get"):
            restaurant_id = auth.get("restaurant_id")

        if restaurant_id is None:
            raise ValidationError("Restaurant context required.")

        reservation = create_reservation(
            restaurant_id=int(restaurant_id),
            customer_id=request.user.pk,  # type: ignore[arg-type]
            table_id=str(serializer.validated_data["table"].public_id),
            guest_count=serializer.validated_data["guest_count"],
            start_at=serializer.validated_data["start_at"],
            end_at=serializer.validated_data["end_at"],
            notes=serializer.validated_data.get("notes"),
        )

        result_serializer = self.get_serializer(reservation)
        return Response(result_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="my")
    def my(self, request: Request) -> Response:
        reservations = get_customer_reservations(request.user.pk)  # type: ignore[arg-type]
        serializer = self.get_serializer(reservations, many=True)
        return Response(serializer.data)
