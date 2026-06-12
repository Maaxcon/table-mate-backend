from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import OrderItemViewSet, OrderViewSet, SessionViewSet, TicketViewSet

router = DefaultRouter()
router.register("sessions", SessionViewSet, basename="session")
router.register("orders", OrderViewSet, basename="order")
router.register("tickets", TicketViewSet, basename="ticket")
router.register("order-items", OrderItemViewSet, basename="order-item")

cart_v1_urls = [
    path("cart/", include("apps.orders.api.v1.urls")),
]

urlpatterns = [
    path("", include(router.urls)),
    path("", include(cart_v1_urls)),
]
