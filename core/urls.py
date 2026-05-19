from django.conf import settings
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path

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

if settings.DEBUG:
    from drf_spectacular.views import (
        SpectacularAPIView,
        SpectacularRedocView,
        SpectacularSwaggerView,
    )

    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path(
            "api/schema/swagger-ui/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
        path(
            "api/schema/redoc/",
            SpectacularRedocView.as_view(url_name="schema"),
            name="redoc",
        ),
    ]
