from typing import ClassVar

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class HasAnyRole(BasePermission):
    roles: ClassVar[frozenset[str]] = frozenset()

    def has_permission(self, request: Request, view: APIView) -> bool:
        u = request.user
        return bool(u and u.is_authenticated and getattr(u, "role", None) in self.roles)
