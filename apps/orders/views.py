from rest_framework import viewsets

from .models import Order, OrderItem, Session, Ticket
from .serializers import (
    OrderItemSerializer,
    OrderSerializer,
    SessionSerializer,
    TicketSerializer,
)


class SessionViewSet(viewsets.ReadOnlyModelViewSet[Session]):
    queryset = Session.objects.all()
    serializer_class = SessionSerializer


class OrderViewSet(viewsets.ReadOnlyModelViewSet[Order]):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer


class TicketViewSet(viewsets.ReadOnlyModelViewSet[Ticket]):
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer


class OrderItemViewSet(viewsets.ReadOnlyModelViewSet[OrderItem]):
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
