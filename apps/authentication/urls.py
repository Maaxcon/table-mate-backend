from django.urls import path

from .views import (
    CookieTokenRefreshView,
    CustomerContextView,
    CustomTokenObtainPairView,
    GoogleAuthView,
    GoogleContextView,
    GuestInitView,
    LogoutView,
    MeView,
)

urlpatterns = [
    path("token/", CustomTokenObtainPairView.as_view(), name="token-obtain"),
    path("refresh/", CookieTokenRefreshView.as_view(), name="token-refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("google/", GoogleAuthView.as_view(), name="google-auth"),
    path("google/context/", GoogleContextView.as_view(), name="google-context"),
    path("customer/context/", CustomerContextView.as_view(), name="customer-context"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("guest-init/", GuestInitView.as_view(), name="guest-init"),
]
