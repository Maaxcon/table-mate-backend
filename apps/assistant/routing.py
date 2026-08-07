from django.urls import path
from django.urls.resolvers import URLPattern

from .consumers import AssistantConsumer

websocket_urlpatterns: list[URLPattern] = [
    path("ws/assistant/<uuid:conversation_id>/", AssistantConsumer.as_asgi()),
]

__all__ = ["websocket_urlpatterns"]
