from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from common.api import PublicLookupMixin

from .models import Order, OrderItem, Session, Ticket
from .serializers import (
    OrderItemSerializer,
    OrderSerializer,
    SessionSerializer,
    TicketSerializer,
)


@extend_schema(tags=["Orders"])
class SessionViewSet(PublicLookupMixin, viewsets.ReadOnlyModelViewSet[Session]):
    queryset = Session.objects.all()
    serializer_class = SessionSerializer


@extend_schema(tags=["Orders"])
class OrderViewSet(PublicLookupMixin, viewsets.ReadOnlyModelViewSet[Order]):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer


@extend_schema(tags=["Orders"])
class TicketViewSet(PublicLookupMixin, viewsets.ReadOnlyModelViewSet[Ticket]):
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer


@extend_schema(tags=["Orders"])
class OrderItemViewSet(PublicLookupMixin, viewsets.ReadOnlyModelViewSet[OrderItem]):
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
