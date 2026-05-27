from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.authentication.models import RoleCode

from .models import Reservation


class CanManageReservations(BasePermission):
    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return getattr(user, "role", None) in {RoleCode.ADMIN, RoleCode.WAITER, RoleCode.CUSTOMER}

    def has_object_permission(self, request: Request, view: APIView, obj: Reservation) -> bool:
        role = getattr(request.user, "role", None)
        if role in {RoleCode.ADMIN, RoleCode.WAITER}:
            return True
        if role == RoleCode.CUSTOMER:
            return bool(obj.customer_id == request.user.pk)
        return False
