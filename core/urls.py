from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.authentication.urls")),
    path("api/restaurants/", include("apps.restaurants.urls")),
    path("api/editor/", include("apps.editor.urls")),
    path("api/reservations/", include("apps.reservations.urls")),
    path("api/orders/", include("apps.orders.urls")),
    path("api/menu/", include("apps.menu.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
