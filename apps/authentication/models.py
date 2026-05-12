from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        WAITER = 'waiter', 'Waiter'
        COOK = 'cook', 'Cook'
        CUSTOMER = 'customer', 'Customer'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)

    def __str__(self) -> str:
        return self.username
