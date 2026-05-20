from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from common.api import RestaurantScopedViewSetMixin

from .models import Payment
from .serializers import PaymentSerializer


@extend_schema(tags=["Payments"])
class PaymentViewSet(
    RestaurantScopedViewSetMixin[Payment],
    viewsets.ReadOnlyModelViewSet[Payment],
):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
