from typing import cast

from django.contrib.auth.models import AbstractBaseUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.tokens import Token

from .models import User


class TokenVersionJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token: Token) -> AbstractBaseUser:
        user = cast(User, super().get_user(validated_token))
        token_version: int | None = validated_token.payload.get("token_version")
        if token_version is not None and user.token_version != token_version:
            raise InvalidToken("Token invalidated due to role change.")
        return user


__all__ = ["TokenVersionJWTAuthentication"]
