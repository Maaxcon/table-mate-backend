from typing import Any, cast

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .models import RoleCode, User


class GoogleAuthSerializer(serializers.Serializer[None]):
    code = serializers.CharField()
    redirect_uri = serializers.CharField()

_STAFF_ROLES: frozenset[str] = frozenset({RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK})


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
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        self._restaurant_id: int | None = attrs.pop("restaurant_id", None)
        data = super().validate(attrs)  # authenticates user; calls get_token()

        user = cast(User, self.user)
        self._validate_restaurant_id(user)

        return data

    def _validate_restaurant_id(self, user: User) -> None:
        if self._restaurant_id is not None:
            if user.restaurant_id != self._restaurant_id:
                raise serializers.ValidationError({"restaurant_id": "User is not a member of this restaurant."})
        elif user.role in _STAFF_ROLES:
            raise serializers.ValidationError({"restaurant_id": "This field is required for staff users."})

    def get_token(self, user: User) -> RefreshToken:  # type: ignore[override]
        token = cast(RefreshToken, super().get_token(user))
        token["role"] = user.role
        if self._restaurant_id is not None:
            token["restaurant_id"] = self._restaurant_id
        return token
