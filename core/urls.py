from django.conf import settings
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)
from rest_framework.permissions import IsAdminUser

urlpatterns: list[URLPattern | URLResolver] = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.authentication.urls")),
    path("api/restaurants/", include("apps.restaurants.urls")),
    path("api/editor/", include("apps.editor.urls")),
    path("api/reservations/", include("apps.reservations.urls")),
    path("api/orders/", include("apps.orders.urls")),
    path("api/menu/", include("apps.menu.urls")),
    path("api/payments/", include("apps.payments.urls")),
]

urlpatterns += [
    path("api/schema/", SpectacularAPIView.as_view(permission_classes=[IsAdminUser]), name="schema"),
]

if settings.DEBUG:
    urlpatterns += [
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    ]
