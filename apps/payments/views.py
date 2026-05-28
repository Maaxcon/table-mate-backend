from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from apps.authentication.permissions import IsAdmin
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
    permission_classes = [IsAdmin]
    filterset_fields = ["order", "provider", "status", "currency"]
    ordering_fields = ["created_at", "updated_at", "amount", "status"]
