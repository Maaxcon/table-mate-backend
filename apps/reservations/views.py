from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from common.api import RestaurantScopedViewSetMixin

from .models import Reservation
from .serializers import ReservationSerializer


@extend_schema(tags=["Reservations"])
class ReservationViewSet(
    RestaurantScopedViewSetMixin[Reservation],
    viewsets.ReadOnlyModelViewSet[Reservation],
):
    queryset = Reservation.objects.all()
    serializer_class = ReservationSerializer
    filterset_fields = ["customer", "table", "status"]
    ordering_fields = ["created_at", "updated_at", "start_at", "end_at", "guest_count"]
