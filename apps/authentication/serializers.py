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
    restaurant_id = serializers.IntegerField(
        required=False, allow_null=True, default=None
    )

    def validate(self, attrs: dict) -> dict:  # type: ignore[override]
        restaurant_id: int | None = attrs.pop("restaurant_id", None)
        data = super().validate(attrs)

        refresh: RefreshToken = RefreshToken.for_user(self.user)
        refresh["role"] = self.user.role
        if restaurant_id is not None:
            refresh["restaurant_id"] = restaurant_id

        data["refresh"] = str(refresh)
        data["access"] = str(refresh.access_token)
        return data
