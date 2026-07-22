import re

from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path, re_path
from django.views.static import serve as serve_static
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
    path("api/receipts/", include("apps.receipts.urls")),
]

urlpatterns += [
    path("api/schema/", SpectacularAPIView.as_view(permission_classes=[IsAdminUser]), name="schema"),
]

if settings.DEBUG:
    urlpatterns += [
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    ]

# No separate media server (nginx/whitenoise) sits in front of the app in any
# environment, so Django has to serve uploaded media itself even in prod.
# django.conf.urls.static.static() no-ops when DEBUG=False, so the view is
# wired up directly here instead.
urlpatterns += [
    re_path(
        rf"^{re.escape(settings.MEDIA_URL.lstrip('/'))}(?P<path>.*)$",
        serve_static,
        {"document_root": settings.MEDIA_ROOT},
    ),
]

# The production stack does not put WhiteNoise or a dedicated static server in
# front of Django, so serve collected static assets from the app itself.
urlpatterns += staticfiles_urlpatterns()
