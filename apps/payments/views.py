from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from .models import Payment, WebhookEvent
from .serializers import PaymentSerializer, WebhookEventSerializer


@extend_schema(tags=["Payments"])
class PaymentViewSet(viewsets.ReadOnlyModelViewSet[Payment]):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer


@extend_schema(tags=["Payments"])
class WebhookEventViewSet(viewsets.ReadOnlyModelViewSet[WebhookEvent]):
    queryset = WebhookEvent.objects.all()
    serializer_class = WebhookEventSerializer
