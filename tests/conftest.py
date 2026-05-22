from collections.abc import Callable
from typing import Any

import factory
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.authentication.models import RoleCode

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):  # type: ignore[type-arg]
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")  # type: ignore[attr-defined, no-untyped-call]
    password = factory.PostGenerationMethodCall("set_password", "password")  # type: ignore[attr-defined, no-untyped-call]
    role = RoleCode.CUSTOMER
    first_name = factory.Faker("first_name")  # type: ignore[attr-defined, no-untyped-call]
    last_name = factory.Faker("last_name")  # type: ignore[attr-defined, no-untyped-call]


@pytest.fixture
def user_factory(db: Any) -> Callable[..., Any]:

    def _factory(role: str = RoleCode.CUSTOMER) -> Any:
        return UserFactory(role=role)  # type: ignore[no-untyped-call]

    return _factory


@pytest.fixture
def api(user_factory: Callable[..., Any]) -> Callable[..., APIClient]:

    def _api(role: str = RoleCode.CUSTOMER) -> APIClient:
        user = user_factory(role=role)
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return _api
