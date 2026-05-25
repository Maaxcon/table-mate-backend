from typing import Any, cast

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User


class UserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = [
            "public_id",
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    restaurant_id = serializers.IntegerField(required=False, allow_null=True, default=None)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        self._restaurant_id: int | None = attrs.pop("restaurant_id", None)
        return super().validate(attrs)

    def get_token(self, user: User) -> RefreshToken:  # type: ignore[override]
        token: RefreshToken = super().get_token(user)
        token["role"] = cast(User, user).role
        if self._restaurant_id is not None:
            token["restaurant_id"] = self._restaurant_id
        return token
