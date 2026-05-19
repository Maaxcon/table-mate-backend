from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import LayoutViewSet

router = DefaultRouter()
router.register("layouts", LayoutViewSet, basename="layout")

urlpatterns = [
    path("", include(router.urls)),
]
