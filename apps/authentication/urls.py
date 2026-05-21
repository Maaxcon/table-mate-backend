from django.urls import URLPattern, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns: list[URLPattern] = [
    path("token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
]
