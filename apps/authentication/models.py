from typing import ClassVar

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from common.models import BaseModel, RestaurantScopedModel


class RoleCode(models.TextChoices):
    ADMIN = "admin", "Admin"
    WAITER = "waiter", "Waiter"
    COOK = "cook", "Cook"
    CUSTOMER = "customer", "Customer"


class ShiftStatus(models.TextChoices):
    OFFLINE = "offline", "Offline"
    ON_SHIFT = "on_shift", "On shift"
    BREAK = "break", "Break"


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: object,
    ) -> "User":
        if not email:
            raise ValueError("Email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        email: str,
        password: str,
        **extra_fields: object,
    ) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        role = Role.objects.filter(code=RoleCode.ADMIN).first()
        if role is not None:
            extra_fields.setdefault("role", role)

        return self.create_user(email, password, **extra_fields)


class Role(BaseModel):
    code = models.CharField(max_length=32, unique=True, choices=RoleCode.choices)
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(code__in=RoleCode.values),
                name="authentication_role_code_valid",
            )
        ]
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.ForeignKey(
        "authentication.Role",
        on_delete=models.PROTECT,
        related_name="users",
    )
    token_version = models.PositiveIntegerField(default=0)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    objects = UserManager()

    USERNAME_FIELD: ClassVar[str] = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.email


class Staff(RestaurantScopedModel):
    user = models.ForeignKey(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="staff_memberships",
    )
    shift_status = models.CharField(
        max_length=20,
        choices=ShiftStatus.choices,
        default=ShiftStatus.OFFLINE,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "restaurant"],
                name="authentication_staff_user_restaurant_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(shift_status__in=ShiftStatus.values),
                name="authentication_staff_shift_status_valid",
            ),
        ]
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.user.email} @ {self.restaurant.name}"


class Customer(BaseModel):
    user = models.OneToOneField(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="customer_profile",
    )
    phone = models.CharField(max_length=32, null=True, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.user.email
