from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PaymentViewSet, WebhookEventViewSet

router = DefaultRouter()
router.register("payments", PaymentViewSet, basename="payment")
router.register("webhook-events", WebhookEventViewSet, basename="webhook-event")

urlpatterns = [
    path("", include(router.urls)),
]
