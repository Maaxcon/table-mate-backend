from django.urls import path

from .consumers import HallConsumer

websocket_urlpatterns = [
    path("ws/hall/", HallConsumer.as_asgi()),
]
