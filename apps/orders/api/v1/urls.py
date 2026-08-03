from django.urls import path

from .views import (
    CartBillView,
    CartCallWaiterView,
    CartCheckoutView,
    CartPayView,
    CartSessionItemViewSet,
    CartSessionViewSet,
    SetGuestNameView,
)

urlpatterns = [
    path("sessions/", CartSessionViewSet.as_view({"get": "list", "post": "create"}), name="cart-session-list"),
    path(
        "sessions/<uuid:pk>/",
        CartSessionViewSet.as_view({"get": "retrieve"}),
        name="cart-session-detail",
    ),
    path(
        "sessions/<uuid:session_pk>/checkout/",
        CartCheckoutView.as_view(),
        name="cart-checkout",
    ),
    path(
        "sessions/<uuid:session_pk>/bill/",
        CartBillView.as_view(),
        name="cart-bill",
    ),
    path(
        "sessions/<uuid:session_pk>/pay/",
        CartPayView.as_view(),
        name="cart-pay",
    ),
    path(
        "sessions/<uuid:session_pk>/items/",
        CartSessionItemViewSet.as_view({"get": "list", "post": "create"}),
        name="cart-item-list",
    ),
    path(
        "sessions/<uuid:session_pk>/items/<uuid:pk>/",
        CartSessionItemViewSet.as_view({"delete": "destroy", "patch": "partial_update"}),
        name="cart-item-detail",
    ),
    path(
        "sessions/<uuid:session_pk>/guest-name/",
        SetGuestNameView.as_view(),
        name="cart-guest-name",
    ),
    path(
        "sessions/<uuid:session_pk>/call-waiter/",
        CartCallWaiterView.as_view(),
        name="cart-call-waiter",
    ),
]
