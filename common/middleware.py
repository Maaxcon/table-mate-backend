from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError

from common.api import reset_current_restaurant_id, set_current_restaurant_id


class RestaurantScopeMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.jwt_auth = JWTAuthentication()

    def __call__(self, request: HttpRequest) -> HttpResponse:
        restaurant_id = self._resolve_restaurant_id(request)
        request.restaurant_id = restaurant_id  # type: ignore[attr-defined]
        token = set_current_restaurant_id(restaurant_id)

        try:
            return self.get_response(request)
        finally:
            reset_current_restaurant_id(token)

    def _resolve_restaurant_id(self, request: HttpRequest) -> int | None:
        authorization = request.META.get("HTTP_AUTHORIZATION")
        if not authorization:
            return None
        if isinstance(authorization, str):
            header = authorization.encode("utf-8")
        else:
            header = authorization

        raw_token = self.jwt_auth.get_raw_token(header)
        if raw_token is None:
            return None

        try:
            validated_token = self.jwt_auth.get_validated_token(raw_token)
        except TokenError:
            return None

        claim_value = validated_token.get("restaurant_id")
        if claim_value is None:
            return None

        try:
            return int(claim_value)
        except (TypeError, ValueError):
            return None
