from django.views import View
from rest_framework import permissions
from rest_framework.request import Request

from apps.orders.models import CartSession, CartSessionStatus


class IsActiveTableGuest(permissions.BasePermission):
    def has_permission(self, request: Request, view: View) -> bool:
        if request.user and request.user.is_authenticated:
            return True

        auth = getattr(request, "auth", None)
        if auth is None:
            return False

        payload = getattr(auth, "payload", {})
        if not payload.get("is_guest"):
            return False

        cart_session_id = payload.get("cart_session_id")
        if cart_session_id is None:
            return False

        return CartSession.objects.filter(
            public_id=cart_session_id,
            status=CartSessionStatus.ACTIVE,
        ).exists()
