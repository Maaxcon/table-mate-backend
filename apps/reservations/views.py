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
