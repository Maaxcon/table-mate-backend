from django.urls import path

from .consumers import FloorConsumer, HallConsumer, NotificationStreamConsumer, StaffReservationsConsumer

websocket_urlpatterns = [
    path("ws/hall/", HallConsumer.as_asgi()),
    path("ws/staff/reservations/", StaffReservationsConsumer.as_asgi()),
    path("ws/staff/notifications/", NotificationStreamConsumer.as_asgi()),
    path("ws/floor/", FloorConsumer.as_asgi()),
]
