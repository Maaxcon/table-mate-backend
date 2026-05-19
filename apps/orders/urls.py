from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import OrderItemViewSet, OrderViewSet, SessionViewSet, TicketViewSet

router = DefaultRouter()
router.register("sessions", SessionViewSet, basename="session")
router.register("orders", OrderViewSet, basename="order")
router.register("tickets", TicketViewSet, basename="ticket")
router.register("order-items", OrderItemViewSet, basename="order-item")

urlpatterns = [
    path("", include(router.urls)),
]
