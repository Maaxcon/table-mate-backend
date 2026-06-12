from typing import cast

from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import Token

from .models import User


class TokenVersionJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token: Token) -> User:  # type: ignore[override]
        user = cast(User, super().get_user(validated_token))
        token_version: int | None = validated_token.payload.get("token_version")
        if token_version is None or user.token_version != token_version:
            raise InvalidToken("Token invalidated due to role change.")
        return user


class GuestJWTAuthentication(BaseAuthentication):
    def authenticate(self, request: Request) -> tuple[AnonymousUser, Token] | None:
        jwt_auth = JWTAuthentication()
        header = jwt_auth.get_header(request)
        if header is None:
            return None
        raw_token = jwt_auth.get_raw_token(header)
        if raw_token is None:
            return None

        try:
            validated_token = jwt_auth.get_validated_token(raw_token)
        except TokenError as exc:
            raise AuthenticationFailed(f"Invalid guest token: {exc}") from exc

        if not validated_token.payload.get("is_guest"):
            return None

        return AnonymousUser(), validated_token


__all__ = ["GuestJWTAuthentication", "TokenVersionJWTAuthentication"]
