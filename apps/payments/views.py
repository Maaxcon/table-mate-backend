from rest_framework import viewsets

from .models import Payment, WebhookEvent
from .serializers import PaymentSerializer, WebhookEventSerializer


class PaymentViewSet(viewsets.ReadOnlyModelViewSet[Payment]):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer


class WebhookEventViewSet(viewsets.ReadOnlyModelViewSet[WebhookEvent]):
    queryset = WebhookEvent.objects.all()
    serializer_class = WebhookEventSerializer
