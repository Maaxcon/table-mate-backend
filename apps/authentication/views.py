import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from django.conf import settings
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import RoleCode, User
from .serializers import CustomTokenObtainPairSerializer, GoogleAuthSerializer, UserSerializer

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def _exchange_google_code(code: str, redirect_uri: str) -> dict[str, Any]:
    payload = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode()
    req = urllib.request.Request(_GOOGLE_TOKEN_URL, data=payload, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())  # type: ignore[no-any-return]
    except urllib.error.HTTPError as exc:
        body: dict[str, Any] = json.loads(exc.read())
        raise ValueError(body.get("error_description", "Google token exchange failed.")) from exc


def _fetch_google_userinfo(access_token: str) -> dict[str, Any]:
    req = urllib.request.Request(
        _GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())  # type: ignore[no-any-return]


def _build_auth_response(user: User) -> Response:
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role  # type: ignore[index]

    response = Response({"access": str(refresh.access_token)})
    response.set_cookie(
        key="refresh_token",
        value=str(refresh),
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Strict",
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
    )
    return response


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class MeView(generics.RetrieveAPIView[User]):
    serializer_class = UserSerializer

    def get_object(self) -> User:
        return self.request.user  # type: ignore[return-value]


class GoogleAuthView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code: str = serializer.validated_data["code"]
        redirect_uri: str = serializer.validated_data["redirect_uri"]

        try:
            token_data = _exchange_google_code(code, redirect_uri)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        google_access_token: str | None = token_data.get("access_token")
        if not google_access_token:
            return Response(
                {"detail": "No access token in Google response."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            userinfo = _fetch_google_userinfo(google_access_token)
        except Exception:
            return Response(
                {"detail": "Failed to fetch Google user info."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email: str | None = userinfo.get("email")
        if not email:
            return Response(
                {"detail": "Google account has no email."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user, _ = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": userinfo.get("given_name", ""),
                "last_name": userinfo.get("family_name", ""),
                "role": RoleCode.CUSTOMER,
            },
        )

        return _build_auth_response(user)


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

        return Response(serializer.validated_data)


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        response = Response(status=status.HTTP_200_OK)
        response.delete_cookie(key="refresh_token", samesite="Strict")
        return response


__all__ = [
    "CustomTokenObtainPairView",
    "MeView",
    "GoogleAuthView",
    "CookieTokenRefreshView",
    "LogoutView",
]
