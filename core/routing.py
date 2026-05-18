import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
import apps.orders.routing as orders_routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.production')

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': URLRouter(
        orders_routing.websocket_urlpatterns
    ),
})
