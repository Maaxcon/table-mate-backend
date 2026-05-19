from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from common.api import PublicLookupMixin

from .models import Reservation
from .serializers import ReservationSerializer


@extend_schema(tags=["Reservations"])
class ReservationViewSet(PublicLookupMixin, viewsets.ReadOnlyModelViewSet[Reservation]):
    queryset = Reservation.objects.all()
    serializer_class = ReservationSerializer
