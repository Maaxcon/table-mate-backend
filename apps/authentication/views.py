from datetime import timedelta
from typing import Any, cast
from uuid import uuid4

from django.conf import settings
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.orders.models import CartSession, CartSessionStatus
from apps.orders.services import ensure_active_cart_for_table
from apps.reservations.models import Reservation
from apps.restaurants.models import Restaurant, Table
from common.exceptions import NoActiveReservationError

from .models import RoleCode, User
from .serializers import (
    CustomerContextSerializer,
    CustomTokenObtainPairSerializer,
    GoogleAuthResponseSerializer,
    GoogleAuthSerializer,
    GoogleContextResponseSerializer,
    GoogleContextSerializer,
    GuestInitSerializer,
    MeUpdateSerializer,
    UserSerializer,
)
from .services import google_authenticate, issue_tokens, issue_tokens_with_restaurant


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
            resolved = Restaurant.objects.filter(public_id=public_id).values_list("id", flat=True).first()
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


class CustomerContextView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=CustomerContextSerializer,
        responses={
            200: GoogleContextResponseSerializer,
            403: OpenApiResponse(description="User is not a participant in this reservation."),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = CustomerContextSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = cast(User, request.user)
        if user.role != RoleCode.CUSTOMER:
            return Response(
                {"detail": "Only customers may use this endpoint."},
                status=status.HTTP_403_FORBIDDEN,
            )

        reservation = serializer.validated_data["reservation"]
        is_customer = reservation.customer_id == user.id
        is_participant = reservation.participants.filter(id=user.id).exists()
        if not (is_customer or is_participant):
            return Response(
                {"detail": "You are not a participant in this reservation."},
                status=status.HTTP_403_FORBIDDEN,
            )

        access, refresh = issue_tokens_with_restaurant(user, reservation.restaurant_id)
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


class GuestInitView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []
    throttle_scope = "auth"

    @extend_schema(
        request=GuestInitSerializer,
        responses={
            200: OpenApiResponse(description="Guest JWT issued."),
            400: OpenApiResponse(description="Invalid request."),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = GuestInitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reservation_id = serializer.validated_data.get("reservation_id")
        table_id = serializer.validated_data.get("table_id")

        session: CartSession | None
        if table_id:
            # Scan flow: create the cart if the table has an active reservation.
            # Raises NoActiveReservationError (-> 404 NO_ACTIVE_RESERVATION) otherwise.
            session = _ensure_session_for_table(str(table_id))
        else:
            session = _find_active_session_for_reservation(reservation_id)
            if session is None:
                return Response(
                    {"detail": "No active cart session found for this reservation."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        cart_session_id = str(session.public_id)
        guest_id = _carry_forward_guest_id(request)
        token = _issue_guest_token(cart_session_id=cart_session_id, guest_id=guest_id)
        return Response({"access": token})


def _ensure_session_for_table(table_id: str) -> CartSession:
    table = Table.objects.filter(public_id=table_id, active=True).first()
    if table is None:
        raise NoActiveReservationError("This table has no active reservation.")
    return ensure_active_cart_for_table(table=table)


def _find_active_session_for_reservation(reservation_id: Any) -> CartSession | None:
    # Reuse the open cart if one exists; otherwise open a fresh one for the
    # reservation's table (e.g. the round after a checkout closed the last cart).
    session = (
        CartSession.objects.filter(
            reservation__public_id=reservation_id,
            status=CartSessionStatus.ACTIVE,
        )
        .order_by("-created_at")
        .first()
    )
    if session is not None:
        return session

    reservation = Reservation.objects.filter(public_id=reservation_id).select_related("table").first()
    if reservation is None or reservation.table is None:
        return None
    try:
        return ensure_active_cart_for_table(table=reservation.table)
    except NoActiveReservationError:
        return None


def _issue_guest_token(*, cart_session_id: str | None, guest_id: str | None = None) -> str:
    from rest_framework_simplejwt.tokens import AccessToken

    token = AccessToken()
    token.payload["is_guest"] = True
    token.payload["guest_id"] = guest_id or str(uuid4())
    if cart_session_id:
        token.payload["cart_session_id"] = cart_session_id
    token.set_exp(lifetime=timedelta(hours=4))
    return str(token)


def _carry_forward_guest_id(request: Request) -> str | None:
    import jwt as pyjwt
    from rest_framework_simplejwt.settings import api_settings

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    raw_token = auth_header[len("Bearer ") :].strip()
    verifying_key = api_settings.VERIFYING_KEY or api_settings.SIGNING_KEY
    try:
        payload = pyjwt.decode(
            raw_token,
            verifying_key,
            algorithms=[api_settings.ALGORITHM],
            options={"verify_exp": False},
        )
    except pyjwt.PyJWTError:
        return None
    if payload.get("is_guest"):
        return payload.get("guest_id")
    return None


__all__ = [
    "CustomTokenObtainPairView",
    "MeView",
    "GoogleAuthView",
    "GoogleContextView",
    "CustomerContextView",
    "CookieTokenRefreshView",
    "LogoutView",
    "GuestInitView",
]
