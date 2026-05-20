import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls.resolvers import URLPattern, URLResolver

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.production")

django_asgi_app = get_asgi_application()

from apps.editor.routing import (  # noqa: E402
    websocket_urlpatterns as editor_ws_patterns,
)
from apps.orders.routing import (  # noqa: E402
    websocket_urlpatterns as orders_ws_patterns,
)

websocket_urlpatterns: list[URLPattern | URLResolver] = [
    *orders_ws_patterns,
    *editor_ws_patterns,
]

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": URLRouter(websocket_urlpatterns),
    }
)
