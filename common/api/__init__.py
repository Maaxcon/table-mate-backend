from typing import ClassVar, Final, Generic, Protocol, TypeVar, cast

from django.db.models import Manager, Model, QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.request import Request

_ModelT = TypeVar("_ModelT", bound=Model)

_UNSET: Final = object()
_CACHE_ATTR: Final = "_resolved_restaurant_id"


class _HasRequest(Protocol):
    request: Request


def get_restaurant_id_from_auth(request: Request) -> int | None:
    auth = getattr(request, "auth", None)
    if auth is not None and hasattr(auth, "get"):
        try:
            val = auth.get("restaurant_id")
            if val is not None:
                return int(val)
        except (TypeError, ValueError, AttributeError):
            pass
    return None


class PublicLookupMixin:
    lookup_field: ClassVar[str] = "public_id"
    lookup_url_kwarg: ClassVar[str | None] = "public_id"
    lookup_value_regex: ClassVar[str] = "[0-9a-fA-F-]{36}"


class PublicRestaurantQueryMixin:
    restaurant_query_param: ClassVar[str] = "restaurant"

    def get_restaurant_id(self) -> int | None:
        from apps.restaurants.models import Restaurant

        request = cast(_HasRequest, self).request
        cached = getattr(request, _CACHE_ATTR, _UNSET)
        if cached is not _UNSET:
            return cached  # type: ignore[return-value]

        public_id = request.query_params.get(self.restaurant_query_param)
        if not public_id:
            setattr(request, _CACHE_ATTR, None)
            return None
        try:
            restaurant_id: int | None = Restaurant.objects.values_list("id", flat=True).get(public_id=public_id)
        except (Restaurant.DoesNotExist, ValueError):
            restaurant_id = None
        setattr(request, _CACHE_ATTR, restaurant_id)
        return restaurant_id

    def resolve_restaurant_or_not_found(self) -> int | None:
        restaurant_id = self.get_restaurant_id()
        if restaurant_id is None:
            public_id = cast(_HasRequest, self).request.query_params.get(self.restaurant_query_param)
            if public_id:
                from django.http import Http404

                raise Http404("Restaurant not found.") from None
        return restaurant_id


@extend_schema_field(OpenApiTypes.UUID)
class PublicIdRelatedField(serializers.SlugRelatedField[_ModelT]):
    def __init__(
        self,
        *,
        read_only: bool = False,
        many: bool = False,
        queryset: QuerySet[_ModelT] | Manager[_ModelT] | None = None,
        required: bool | None = None,
        allow_null: bool = False,
    ) -> None:
        super().__init__(
            slug_field="public_id",
            read_only=read_only,
            many=many,
            queryset=queryset,
            required=required,
            allow_null=allow_null,
        )


class RestaurantScopedViewSetMixin(PublicLookupMixin, Generic[_ModelT]):
    restaurant_lookup: ClassVar[str] = "restaurant_id"

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "get_queryset" in cls.__dict__:
            raise TypeError(f"{cls.__name__}: override safely_get_queryset() instead of get_queryset()")

    def get_queryset(self) -> QuerySet[_ModelT]:
        queryset = cast(QuerySet[_ModelT], super().get_queryset())  # type: ignore[misc]
        request = cast(_HasRequest, self).request
        restaurant_id = get_restaurant_id_from_auth(request)

        if restaurant_id is None:
            return queryset.none()

        return self.safely_get_queryset(queryset.filter(**{self.restaurant_lookup: restaurant_id}))

    def safely_get_queryset(self, qs: QuerySet[_ModelT]) -> QuerySet[_ModelT]:
        return qs
