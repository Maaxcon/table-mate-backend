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


class IsFloorOrCustomer(HasAnyRole):
    """Floor staff and customers; admin is always included."""

    roles = frozenset({RoleCode.ADMIN, RoleCode.WAITER, RoleCode.CUSTOMER})
