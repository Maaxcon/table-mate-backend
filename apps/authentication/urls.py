from django.urls import path

from .views import (
    CookieTokenRefreshView,
    CustomTokenObtainPairView,
    GoogleAuthView,
    LogoutView,
    MeView,
)

urlpatterns = [
    path("token/", CustomTokenObtainPairView.as_view(), name="token-obtain"),
    path("refresh/", CookieTokenRefreshView.as_view(), name="token-refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("google/", GoogleAuthView.as_view(), name="google-auth"),
    path("logout/", LogoutView.as_view(), name="logout"),
]
