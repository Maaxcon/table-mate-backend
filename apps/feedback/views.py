from datetime import datetime
from typing import Any
from uuid import UUID

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.authentication.authentication import GuestJWTAuthentication, TokenVersionJWTAuthentication
from apps.authentication.models import User
from apps.authentication.permissions import IsAdmin
from common.api import RestaurantScopedViewSetMixin
from common.exceptions import DomainError

from .models import Feedback, FeedbackReviewStatus
from .selectors import get_feedback_list, get_guest_feedback_list
from .serializers import (
    FeedbackDetailSerializer,
    FeedbackListSerializer,
    GuestFeedbackCreateSerializer,
    GuestFeedbackListSerializer,
)
from .services import create_feedback, mark_feedback_reviewed, update_feedback

_ALLOWED_ORDERING_FIELDS = frozenset(
    {"id", "created_at", "updated_at", "overall_rating", "service_rating", "review_status"}
)


def _parse_optional_int(value: str | None, *, field: str) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        raise ValidationError(f"{field} must be an integer.") from None
    if not 1 <= parsed <= 5:
        raise ValidationError(f"{field} must be between 1 and 5.")
    return parsed


def _parse_optional_datetime(value: str | None, *, field: str) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{field} must be a valid ISO-8601 date or datetime.") from None


def _parse_optional_uuid(value: str | None, *, field: str) -> str | None:
    if value is None:
        return None
    try:
        UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise ValidationError(f"{field} must be a valid UUID.") from None
    return value


def _parse_ordering(value: str | None) -> list[str] | None:
    if value is None:
        return None
    fields: list[str] = []
    for token in value.split(","):
        field = token.strip()
        if not field:
            continue
        name = field[1:] if field.startswith("-") else field
        if name not in _ALLOWED_ORDERING_FIELDS:
            raise ValidationError(f"Invalid ordering field: {field!r}.")
        fields.append(field)
    return fields


class IsAuthenticatedOrTableGuest(BasePermission):
    def has_permission(self, request: Request, view: object) -> bool:
        if request.user and request.user.is_authenticated:
            return True
        return bool(getattr(request.auth, "payload", {}).get("is_guest"))


@extend_schema(tags=["Feedback Admin"])
class AdminFeedbackViewSet(
    RestaurantScopedViewSetMixin[Feedback],
    viewsets.ModelViewSet[Feedback],
):
    permission_classes = [IsAuthenticated, IsAdmin]
    queryset = Feedback.objects.all()
    restaurant_lookup = "restaurant_id"
    http_method_names = ["get", "head", "options"]

    def get_serializer_class(
        self,
    ) -> type[FeedbackDetailSerializer] | type[FeedbackListSerializer]:
        if self.action == "retrieve":
            return FeedbackDetailSerializer
        return FeedbackListSerializer

    def safely_get_queryset(self, qs: QuerySet[Feedback]) -> QuerySet[Feedback]:
        review_status = self.request.query_params.get("review_status")
        if review_status is not None and review_status not in FeedbackReviewStatus.values:
            raise ValidationError("review_status must be 'new' or 'reviewed'.")
        overall_rating = _parse_optional_int(
            self.request.query_params.get("overall_rating"),
            field="overall_rating",
        )
        service_rating = _parse_optional_int(
            self.request.query_params.get("service_rating"),
            field="service_rating",
        )
        dish_id = _parse_optional_uuid(self.request.query_params.get("dish_id"), field="dish_id")
        date_from = _parse_optional_datetime(
            self.request.query_params.get("date_from"),
            field="date_from",
        )
        date_to = _parse_optional_datetime(self.request.query_params.get("date_to"), field="date_to")
        ordering = _parse_ordering(self.request.query_params.get("ordering"))

        return get_feedback_list(
            queryset=qs,
            review_status=review_status,
            overall_rating=overall_rating,
            service_rating=service_rating,
            dish_id=dish_id,
            date_from=date_from,
            date_to=date_to,
            ordering=ordering,
        )

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        feedback = self.get_object()
        feedback = mark_feedback_reviewed(feedback=feedback)
        return Response(FeedbackDetailSerializer(feedback).data, status=status.HTTP_200_OK)


@extend_schema(tags=["Feedback"])
class GuestFeedbackViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet[Feedback],
):
    permission_classes = [IsAuthenticatedOrTableGuest]
    authentication_classes = [GuestJWTAuthentication, TokenVersionJWTAuthentication]
    serializer_class = GuestFeedbackListSerializer
    lookup_field = "public_id"
    lookup_url_kwarg = "pk"

    def _get_guest(self, request: Request) -> User | None:
        return request.user if request.user.is_authenticated else None

    def _get_guest_identity(self, request: Request) -> str | None:
        auth = getattr(request, "auth", None)
        if auth is not None and getattr(auth, "payload", {}).get("is_guest"):
            guest_identity = auth.payload.get("guest_id")
            return guest_identity if isinstance(guest_identity, str) else None
        return None

    def get_serializer_class(self) -> type[serializers.BaseSerializer[Any]]:
        if self.action == "create":
            return GuestFeedbackCreateSerializer
        return GuestFeedbackListSerializer

    def get_queryset(self) -> QuerySet[Feedback]:
        guest = self._get_guest(self.request)
        return get_guest_feedback_list(
            guest_id=guest.id if guest else None,
            guest_identity=self._get_guest_identity(self.request),
        )

    @extend_schema(
        request=GuestFeedbackCreateSerializer,
        responses={201: GuestFeedbackListSerializer},
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = GuestFeedbackCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        guest = self._get_guest(request)
        guest_identity = self._get_guest_identity(request)

        try:
            feedback = create_feedback(
                guest=guest,
                guest_identity=guest_identity,
                order_id=serializer.validated_data["order"],
                overall_rating=serializer.validated_data["overall_rating"],
                service_rating=serializer.validated_data["service_rating"],
                comment=serializer.validated_data.get("comment", ""),
                dish_feedback_data=serializer.validated_data.get("dish_feedback"),
            )
        except DomainError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        result = GuestFeedbackListSerializer(feedback)
        return Response(result.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=GuestFeedbackCreateSerializer,
        responses={200: GuestFeedbackListSerializer},
    )
    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        feedback = self.get_object()

        serializer = GuestFeedbackCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            feedback = update_feedback(
                feedback=feedback,
                overall_rating=serializer.validated_data["overall_rating"],
                service_rating=serializer.validated_data["service_rating"],
                comment=serializer.validated_data.get("comment", ""),
                dish_feedback_data=serializer.validated_data.get("dish_feedback"),
            )
        except DomainError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        result = GuestFeedbackListSerializer(feedback)
        return Response(result.data, status=status.HTTP_200_OK)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        feedback = self.get_object()
        feedback.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
