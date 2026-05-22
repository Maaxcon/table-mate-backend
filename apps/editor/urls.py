from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import EditorTableViewSet, LayoutViewSet

router = DefaultRouter()
router.register("layouts", LayoutViewSet, basename="layout")
router.register("tables", EditorTableViewSet, basename="editor-table")

urlpatterns = [
    path("", include(router.urls)),
]
