from django.urls import path

from .views import CartSessionItemViewSet, CartSessionViewSet

urlpatterns = [
    path("sessions/", CartSessionViewSet.as_view({"get": "list", "post": "create"}), name="cart-session-list"),
    path("sessions/<uuid:pk>/", CartSessionViewSet.as_view({"get": "retrieve"}), name="cart-session-detail"),
    path(
        "sessions/<uuid:session_pk>/items/",
        CartSessionItemViewSet.as_view({"get": "list", "post": "create"}),
        name="cart-item-list",
    ),
    path(
        "sessions/<uuid:session_pk>/items/<uuid:pk>/",
        CartSessionItemViewSet.as_view({"delete": "destroy"}),
        name="cart-item-detail",
    ),
]
