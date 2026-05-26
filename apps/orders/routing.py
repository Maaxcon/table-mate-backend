from django.urls import path

from .consumers import CartConsumer

websocket_urlpatterns = [
    path("ws/cart/<uuid:session_id>/", CartConsumer.as_asgi()),
]
