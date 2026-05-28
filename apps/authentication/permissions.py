from apps.authentication.models import RoleCode
from common.permissions import HasAnyRole


class IsAdmin(HasAnyRole):
    roles = frozenset({RoleCode.ADMIN})


class IsStaff(HasAnyRole):
    roles = frozenset({RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK})


class IsKitchen(HasAnyRole):
    roles = frozenset({RoleCode.ADMIN, RoleCode.COOK})


class IsFloor(HasAnyRole):
    roles = frozenset({RoleCode.ADMIN, RoleCode.WAITER})


class IsCustomer(HasAnyRole):
    roles = frozenset({RoleCode.CUSTOMER})


class IsNonKitchen(HasAnyRole):
    """Everyone except kitchen staff — admin, waiter, and customer."""

    roles = frozenset({RoleCode.ADMIN, RoleCode.WAITER, RoleCode.CUSTOMER})
