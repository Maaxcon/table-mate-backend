# ws/cart/ routing removed — cart is now offline-first.
# ws/hall/ routing lives in apps/editor/routing.py

from django.urls import URLPattern, URLResolver

websocket_urlpatterns: list[URLPattern | URLResolver] = []
