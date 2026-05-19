from apps.authentication.models import RoleCode
from common.permissions import HasRole


class IsAdmin(HasRole):
    role = RoleCode.ADMIN


class IsWaiter(HasRole):
    role = RoleCode.WAITER


class IsCook(HasRole):
    role = RoleCode.COOK


class IsCustomer(HasRole):
    role = RoleCode.CUSTOMER
