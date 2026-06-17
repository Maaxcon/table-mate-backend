from django.urls import path

from .consumers import FloorConsumer, HallConsumer

websocket_urlpatterns = [
    path("ws/hall/", HallConsumer.as_asgi()),
    path("ws/floor/", FloorConsumer.as_asgi()),
]
