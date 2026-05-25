from typing import ClassVar

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class HasAnyRole(BasePermission):
    roles: ClassVar[frozenset[str]] = frozenset()

    def has_permission(self, request: Request, view: APIView) -> bool:
        u = request.user
        return bool(u and u.is_authenticated and getattr(u, "role", None) in self.roles)

    _cache: dict[frozenset[str], "HasAnyRole"] = {}

    @classmethod
    def with_roles(cls, *roles: str) -> "HasAnyRole":
        key = frozenset(roles)
        if key not in cls._cache:
            new_cls = type(f"Has{''.join(r.capitalize() for r in roles)}Role", (cls,), {"roles": key})
            cls._cache[key] = new_cls()
        return cls._cache[key]
