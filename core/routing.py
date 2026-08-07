import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls.resolvers import URLPattern, URLResolver

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.production")

django_asgi_app = get_asgi_application()

# Consumers reference models; Django apps must be fully populated first.
# get_asgi_application() triggers apps.populate(), so these must come after.
from apps.editor.routing import (  # noqa: E402
    websocket_urlpatterns as editor_ws_patterns,
)
from apps.orders.routing import (  # noqa: E402
    websocket_urlpatterns as orders_ws_patterns,
)
from apps.assistant.routing import (  # noqa: E402
    websocket_urlpatterns as assistant_ws_patterns,
)

websocket_urlpatterns: list[URLPattern | URLResolver] = [
    *editor_ws_patterns,
    *orders_ws_patterns,
    *assistant_ws_patterns,
]

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": URLRouter(websocket_urlpatterns),
    }
)
