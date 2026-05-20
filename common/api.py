from contextvars import ContextVar, Token
from typing import ClassVar, Generic, Protocol, TypeVar, cast

from django.db.models import Model, QuerySet
from rest_framework import serializers
from rest_framework.request import Request

_ModelT = TypeVar("_ModelT", bound=Model)


class _HasRequest(Protocol):
    request: Request


class PublicLookupMixin:
    lookup_field: ClassVar[str] = "public_id"
    lookup_url_kwarg: ClassVar[str | None] = "public_id"
    lookup_value_regex: ClassVar[str] = "[0-9a-fA-F-]{36}"


_current_restaurant_id: ContextVar[int | None] = ContextVar(
    "current_restaurant_id",
    default=None,
)


def set_current_restaurant_id(restaurant_id: int | None) -> Token[int | None]:
    return _current_restaurant_id.set(restaurant_id)


def reset_current_restaurant_id(token: Token[int | None]) -> None:
    _current_restaurant_id.reset(token)


def get_current_restaurant_id() -> int | None:
    return _current_restaurant_id.get()


class RestaurantScopedViewSetMixin(PublicLookupMixin, Generic[_ModelT]):
    restaurant_lookup: ClassVar[str] = "restaurant_id"

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "get_queryset" in cls.__dict__:
            raise TypeError(
                f"{cls.__name__}: override safely_get_queryset() "
                "instead of get_queryset()"
            )

    def get_queryset(self) -> QuerySet[_ModelT]:
        queryset = cast(QuerySet[_ModelT], super().get_queryset())  # type: ignore[misc]
        request = cast(_HasRequest, self).request
        restaurant_id = getattr(request, "restaurant_id", None)

        if restaurant_id is None:
            restaurant_id = get_current_restaurant_id()

        if restaurant_id is None:
            return queryset.none()

        return self.safely_get_queryset(
            queryset.filter(**{self.restaurant_lookup: restaurant_id})
        )

    def safely_get_queryset(self, qs: QuerySet[_ModelT]) -> QuerySet[_ModelT]:
        return qs


class RestaurantScopedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField[Model]):
    restaurant_lookup: ClassVar[str] = "restaurant_id"

    def get_queryset(self) -> QuerySet[Model] | None:
        queryset = super().get_queryset()
        restaurant_id = get_current_restaurant_id()

        if queryset is None:
            return None
        if restaurant_id is None:
            return queryset.none()

        return queryset.filter(**{self.restaurant_lookup: restaurant_id})
