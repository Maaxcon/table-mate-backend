from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from common.api import PublicLookupMixin

from .models import Payment
from .serializers import PaymentSerializer


@extend_schema(tags=["Payments"])
class PaymentViewSet(PublicLookupMixin, viewsets.ReadOnlyModelViewSet[Payment]):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
