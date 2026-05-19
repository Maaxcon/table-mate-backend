import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls.resolvers import URLPattern, URLResolver

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.production")

django_asgi_app = get_asgi_application()

websocket_urlpatterns: list[URLPattern | URLResolver] = []

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": URLRouter(websocket_urlpatterns),
    }
)
