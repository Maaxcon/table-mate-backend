from typing import Any, cast

from django.conf import settings
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.restaurants.models import Restaurant

from .models import RoleCode, User
from .serializers import (
    CustomTokenObtainPairSerializer,
    GoogleAuthResponseSerializer,
    GoogleAuthSerializer,
    GoogleContextResponseSerializer,
    GoogleContextSerializer,
    MeUpdateSerializer,
    UserSerializer,
)
from .services import google_authenticate, issue_access_token, issue_tokens, issue_tokens_with_restaurant


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Strict",
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
    )


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    throttle_scope = "auth"


class MeView(generics.RetrieveUpdateAPIView[User]):
    http_method_names = ["get", "patch", "head", "options"]
    throttle_scope = "me_write"

    def get_throttles(self) -> list[BaseThrottle]:
        # Only rate-limit writes; GET /me/ runs on every app load.
        if self.request.method == "PATCH":
            return super().get_throttles()
        return []

    def get_object(self) -> User:
        return self.request.user  # type: ignore[return-value]

    def get_serializer_class(self) -> type[UserSerializer] | type[MeUpdateSerializer]:
        if self.request.method == "PATCH":
            return MeUpdateSerializer
        return UserSerializer

    def partial_update(self, request: Request, *args: object, **kwargs: object) -> Response:
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # Return the full profile so the client can refresh its state in one round-trip.
        return Response(UserSerializer(instance).data)


class GoogleAuthView(APIView):
    permission_classes = [AllowAny]
    serializer_class = GoogleAuthSerializer
    throttle_scope = "auth"

    @extend_schema(
        request=GoogleAuthSerializer,
        responses={
            200: GoogleAuthResponseSerializer,
            400: OpenApiResponse(description="Google authentication failed."),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = google_authenticate(
                code=serializer.validated_data["code"],
                redirect_uri=serializer.validated_data["redirect_uri"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if user.role != RoleCode.CUSTOMER:
            access = issue_access_token(user)
            return Response({"access": access, "needs_restaurant_context": True})

        access, refresh = issue_tokens(user)
        response = Response({"access": access})
        _set_refresh_cookie(response, refresh)
        return response


class GoogleContextView(APIView):
    @extend_schema(
        request=GoogleContextSerializer,
        responses={
            200: GoogleContextResponseSerializer,
            400: OpenApiResponse(description="User is not a member of this restaurant."),
            404: OpenApiResponse(description="Restaurant not found."),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = GoogleContextSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        public_id = serializer.validated_data.get("restaurant_public_id")
        if public_id is not None:
            resolved = (
                Restaurant.objects.filter(public_id=public_id).values_list("id", flat=True).first()
            )
            if resolved is None:
                return Response(
                    {"detail": "Restaurant not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            restaurant_id: int = resolved
        else:
            restaurant_id = serializer.validated_data["restaurant_id"]
        user = cast(User, request.user)

        if user.role == RoleCode.CUSTOMER:
            return Response(
                {"detail": "This endpoint is not available for customer accounts."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if user.restaurant_id != restaurant_id:
            return Response(
                {"detail": "You do not have access to this restaurant."},
                status=status.HTTP_403_FORBIDDEN,
            )

        access, refresh = issue_tokens_with_restaurant(user, restaurant_id)
        response = Response({"access": access})
        _set_refresh_cookie(response, refresh)
        return response


class CookieTokenRefreshView(TokenRefreshView):
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        refresh_token = request.COOKIES.get("refresh_token")
        if not refresh_token:
            return Response({"detail": "No refresh token."}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = self.get_serializer(data={"refresh": refresh_token})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc

        response_data = dict(serializer.validated_data)
        new_refresh = response_data.pop("refresh", None)
        response = Response(response_data)
        if new_refresh:
            _set_refresh_cookie(response, new_refresh)
        return response


class LogoutView(APIView):
    permission_classes = [AllowAny]
    serializer_class = None

    @extend_schema(
        request=None,
        responses={200: OpenApiResponse(description="Refresh token cookie cleared.")},
    )
    def post(self, request: Request) -> Response:
        raw_refresh = request.COOKIES.get("refresh_token")
        if raw_refresh:
            try:
                RefreshToken(raw_refresh).blacklist()  # type: ignore[arg-type]
            except TokenError:
                pass  # already expired or invalid — still clear the cookie
        response = Response(status=status.HTTP_200_OK)
        response.delete_cookie(key="refresh_token", samesite="Strict")
        return response


__all__ = [
    "CustomTokenObtainPairView",
    "MeView",
    "GoogleAuthView",
    "GoogleContextView",
    "CookieTokenRefreshView",
    "LogoutView",
]
