from django.urls import URLPattern, URLResolver, path
from rest_framework.routers import DefaultRouter

from .views import AdminFeedbackViewSet, GuestFeedbackViewSet

router = DefaultRouter()
router.register("admin", AdminFeedbackViewSet, basename="admin-feedback")

urlpatterns: list[URLPattern | URLResolver] = [
    path("", GuestFeedbackViewSet.as_view({"post": "create"}), name="guest-feedback-create"),
    path("my/", GuestFeedbackViewSet.as_view({"get": "list"}), name="guest-feedback-list"),
    path(
        "my/<uuid:pk>/",
        GuestFeedbackViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "delete": "destroy",
            }
        ),
        name="guest-feedback-detail",
    ),
]

urlpatterns += router.urls
