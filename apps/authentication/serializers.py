from typing import Any, cast

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.reservations.models import Reservation
from common.api import PublicIdRelatedField, resolve_restaurant_public_id

from .models import RoleCode, User


class GuestInitSerializer(serializers.Serializer[None]):
    device_id = serializers.CharField(max_length=255, required=False, allow_blank=True)
    reservation_id = serializers.UUIDField(required=False)
    table_id = serializers.UUIDField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs.get("reservation_id") and not attrs.get("table_id"):
            raise serializers.ValidationError("Provide reservation_id or table_id.")
        return attrs


class GoogleAuthSerializer(serializers.Serializer[None]):
    code = serializers.CharField()
    redirect_uri = serializers.CharField()


class GoogleAuthResponseSerializer(serializers.Serializer[None]):
    access = serializers.CharField(read_only=True)
    needs_restaurant_context = serializers.BooleanField(read_only=True, required=False)


class GoogleContextSerializer(serializers.Serializer[None]):
    restaurant_id = serializers.IntegerField(required=False)
    restaurant_public_id = serializers.UUIDField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("restaurant_id") is None and attrs.get("restaurant_public_id") is None:
            raise serializers.ValidationError("Provide restaurant_id or restaurant_public_id.")
        return attrs


class GoogleContextResponseSerializer(serializers.Serializer[None]):
    access = serializers.CharField(read_only=True)


_STAFF_ROLES: frozenset[str] = frozenset({RoleCode.ADMIN, RoleCode.WAITER, RoleCode.COOK})


class CustomerContextSerializer(serializers.Serializer[None]):
    reservation = PublicIdRelatedField[Reservation](
        queryset=Reservation.objects.select_related("restaurant").all(),
        required=True,
    )


class UserSerializer(serializers.ModelSerializer[User]):
    restaurant_public_id = serializers.SerializerMethodField()

    def get_restaurant_public_id(self, obj: User) -> str | None:
        if obj.restaurant is not None:
            return str(obj.restaurant.public_id)
        return None

    class Meta:
        model = User
        fields = [
            "public_id",
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "restaurant_public_id",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class MeUpdateSerializer(serializers.ModelSerializer[User]):
    """Fields a user may edit about themselves.

    Deliberately excludes role, is_active and restaurant so a customer cannot
    escalate their own privileges. Email is NOT editable: it is the Google
    sign-in identity, so changing it would lock the user out / create a
    duplicate account on the next login.
    """

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone"]
        extra_kwargs = {
            "first_name": {"required": False},
            "last_name": {"required": False},
        }


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
        token["token_version"] = user.token_version
        if self._restaurant_id is not None:
            token["restaurant_id"] = self._restaurant_id
            token["restaurant_public_id"] = resolve_restaurant_public_id(self._restaurant_id)
        return token
