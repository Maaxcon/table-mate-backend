from datetime import datetime

from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.authentication.models import RoleCode
from apps.authentication.permissions import IsAdmin, IsFloor
from apps.reservations.models import Reservation
from apps.restaurants.models import Restaurant, Table
from common.api import (
    PublicLookupMixin,
    PublicRestaurantQueryMixin,
    RestaurantScopedViewSetMixin,
    get_restaurant_id_from_auth,
    get_restaurant_public_id_from_auth,
    require_restaurant_id_from_auth,
    resolve_restaurant_public_id,
)
from common.permissions import HasAnyRole

from .models import Layout, LayoutDraft, LayoutVersion
from .selectors import get_available_tables
from .serializers import (
    DraftLayoutSerializer,
    EditorTableSerializer,
    LayoutSerializer,
    LayoutVersionSerializer,
    PublishLayoutSerializer,
)
from .services import LayoutVersionConflictError, TableInUseError, delete_draft, publish_layout, save_draft


@extend_schema(tags=["Editor"])
class LayoutViewSet(RestaurantScopedViewSetMixin[Layout], viewsets.ReadOnlyModelViewSet[Layout]):
    permission_classes = [IsFloor]
    queryset = Layout.objects.all()
    serializer_class = LayoutSerializer
    filterset_fields = ["version", "published_at", "published_by"]
    ordering_fields = ["created_at", "updated_at", "version", "published_at"]

    @extend_schema(
        request=PublishLayoutSerializer,
        responses={201: LayoutVersionSerializer},
    )
    @action(detail=False, methods=["post"], permission_classes=[IsAdmin])
    def publish(self, request: Request) -> Response:
        restaurant_id = require_restaurant_id_from_auth(request)
        # Older tokens carry restaurant_id but not the public_id claim; derive it
        # from the resolved restaurant instead of hard-failing on a stale token.
        restaurant_public_id = get_restaurant_public_id_from_auth(request) or resolve_restaurant_public_id(
            restaurant_id
        )
        serializer = PublishLayoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        base_layout_version_id = serializer.validated_data.pop("base_layout_version_id")

        try:
            result = publish_layout(
                restaurant_id=restaurant_id,
                restaurant_public_id=restaurant_public_id,
                layout_data=serializer.validated_data,
                published_by=request.user,  # type: ignore[arg-type]
                base_layout_version_id=base_layout_version_id,
            )
        except TableInUseError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LayoutVersionConflictError as exc:
            return Response(
                {"detail": str(exc), "current_layout_version_id": exc.current_version_id},
                status=status.HTTP_409_CONFLICT,
            )

        version = result["version"]
        output = LayoutVersionSerializer(version)
        return Response(
            {
                **output.data,
                "table_id_map": result["table_id_map"],
                "public_number_map": result.get("public_number_map", {}),
            },
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Latest published layout JSON",
        description="Returns the layout_json from the most recent LayoutVersion for the admin editor.",
        responses={200: dict},
    )
    @action(detail=False, methods=["get"], url_path="latest", permission_classes=[IsFloor])
    def latest(self, request: Request) -> Response:
        restaurant_id = get_restaurant_id_from_auth(request)
        if restaurant_id is None:
            return Response({"layout_json": None, "layout_version_id": None})

        latest = LayoutVersion.objects.filter(restaurant_id=restaurant_id).order_by("-published_at", "-id").first()
        return Response(
            {
                "layout_json": latest.layout_json if latest else None,
                "layout_version_id": str(latest.public_id) if latest else None,
            }
        )

    # ------------------------------------------------------------------
    # Draft mode — save/load/discard layout draft without publishing
    # ------------------------------------------------------------------

    @extend_schema(
        summary="Floor plan draft",
        description=(
            "GET: load the current admin's draft (or latest published if no draft). "
            "PUT: save a draft (validates same schema as publish, no Table/Zone side effects). "
            "DELETE: discard the current draft."
        ),
        request=PublishLayoutSerializer,
        responses={200: DraftLayoutSerializer, 204: None},
    )
    @action(
        detail=False,
        methods=["get", "put", "delete"],
        url_path="draft",
        permission_classes=[],  # checked manually per-method below
    )
    def draft(self, request: Request) -> Response:
        # Authenticated check for all methods
        if not request.user or not request.user.is_authenticated:
            self.permission_denied(request)

        if request.method == "GET":
            if not IsAdmin().has_permission(request, self):
                self.permission_denied(request)
            return self._get_draft(request)
        elif request.method == "PUT":
            # Only admin can save drafts
            if not IsAdmin().has_permission(request, self):
                self.permission_denied(request)
            return self._put_draft(request)
        elif request.method == "DELETE":
            # Only admin can delete drafts
            if not IsAdmin().has_permission(request, self):
                self.permission_denied(request)
            return self._delete_draft(request)
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def _get_draft(self, request: Request) -> Response:
        restaurant_id = get_restaurant_id_from_auth(request)
        if restaurant_id is None:
            return Response(
                {
                    "draft_json": None,
                    "is_draft": False,
                    "base_layout_version_id": None,
                    "updated_at": None,
                    "owner_id": None,
                }
            )

        draft = LayoutDraft.objects.filter(restaurant_id=restaurant_id, owner_id=request.user.pk).first()
        if draft is not None:
            return Response(
                {
                    "draft_json": draft.draft_json,
                    "is_draft": True,
                    "base_layout_version_id": str(draft.base_version.public_id) if draft.base_version else None,
                    "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
                    "owner_id": str(draft.owner_id) if draft.owner_id else None,
                }
            )

        latest = LayoutVersion.objects.filter(restaurant_id=restaurant_id).order_by("-published_at", "-id").first()
        return Response(
            {
                "draft_json": latest.layout_json if latest else None,
                "is_draft": False,
                "base_layout_version_id": str(latest.public_id) if latest else None,
                "updated_at": None,
                "owner_id": None,
            }
        )

    def _put_draft(self, request: Request) -> Response:
        restaurant_id = require_restaurant_id_from_auth(request)
        serializer = PublishLayoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        base_version_id = serializer.validated_data.pop("base_layout_version_id")

        try:
            draft = save_draft(
                restaurant_id=restaurant_id,
                draft_data=serializer.validated_data,
                owner=request.user,  # type: ignore[arg-type]
                base_version_id=base_version_id,
            )
        except LayoutVersionConflictError as exc:
            return Response(
                {"detail": str(exc), "current_layout_version_id": exc.current_version_id},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {
                "draft_json": draft.draft_json,
                "is_draft": True,
                "base_layout_version_id": str(draft.base_version.public_id) if draft.base_version else None,
                "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
                "owner_id": str(draft.owner_id) if draft.owner_id else None,
            }
        )

    def _delete_draft(self, request: Request) -> Response:
        restaurant_id = get_restaurant_id_from_auth(request)
        owner_id = request.user.pk
        if restaurant_id is not None and owner_id is not None:
            delete_draft(restaurant_id=restaurant_id, owner_id=owner_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Editor"])
class EditorTableViewSet(
    PublicLookupMixin,
    PublicRestaurantQueryMixin,
    viewsets.ModelViewSet[Table],
):
    queryset = Table.objects.all()
    serializer_class = EditorTableSerializer
    http_method_names = ["get", "patch", "head", "options"]
    filterset_fields = ["capacity", "active"]
    ordering_fields = [
        "created_at",
        "updated_at",
        "public_number",
        "capacity",
    ]

    def get_queryset(self) -> QuerySet[Table]:
        qs = super().get_queryset()
        restaurant_id = get_restaurant_id_from_auth(self.request)
        if restaurant_id is None:
            restaurant_id = self.get_restaurant_id()
        if restaurant_id is not None:
            qs = qs.filter(restaurant_id=restaurant_id)
        return qs.filter(active=True)

    def get_permissions(self) -> list[BasePermission]:
        if self.action == "available":
            return []
        return [IsAuthenticated(), HasAnyRole.with_roles(RoleCode.ADMIN, RoleCode.WAITER)]

    def _resolve_restaurant_id(self, request: Request) -> int | None:
        restaurant_id = get_restaurant_id_from_auth(request)
        if restaurant_id is not None:
            return restaurant_id
        public_id = request.query_params.get(self.restaurant_query_param)
        if public_id:
            try:
                return Restaurant.objects.values_list("id", flat=True).get(public_id=public_id)
            except Restaurant.DoesNotExist:
                pass
        return None

    @extend_schema(
        responses=EditorTableSerializer(many=True),
        parameters=[
            OpenApiParameter(name="start_at", type=str, required=True, description="ISO 8601 datetime"),
            OpenApiParameter(name="end_at", type=str, required=True, description="ISO 8601 datetime"),
            OpenApiParameter(name="guest_count", type=int, required=False),
            OpenApiParameter(
                name="exclude",
                type=str,
                required=False,
                description="Reservation public ID to exclude when checking an existing booking.",
            ),
            OpenApiParameter(
                name="restaurant",
                type=str,
                required=False,
                description="Restaurant public ID for unauthenticated access",
            ),
        ],
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="available",
        filter_backends=[],
        authentication_classes=[],
    )
    def available(self, request: Request) -> Response:
        restaurant_id = self._resolve_restaurant_id(request)

        if restaurant_id is None:
            return Response(
                {"detail": "Restaurant context required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_at = request.query_params.get("start_at")
        end_at = request.query_params.get("end_at")
        guest_count = request.query_params.get("guest_count")
        exclude_public_id = request.query_params.get("exclude")

        if not start_at or not end_at:
            return Response(
                {"detail": "start_at and end_at query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            start_dt = datetime.fromisoformat(start_at)
            end_dt = datetime.fromisoformat(end_at)
        except (ValueError, TypeError):
            return Response(
                {"detail": "Invalid date format. Use ISO 8601."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if start_dt >= end_dt:
            return Response(
                {"detail": "start_at must be before end_at."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            gc = int(guest_count) if guest_count else None
        except ValueError:
            return Response({"detail": "guest_count must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
        current_reservation_id = None
        if exclude_public_id:
            current_reservation_id = (
                Reservation.objects.filter(
                    public_id=exclude_public_id,
                    restaurant_id=restaurant_id,
                )
                .values_list("id", flat=True)
                .first()
            )
        tables = get_available_tables(
            restaurant_id=restaurant_id,
            start_at=start_dt,
            end_at=end_dt,
            guest_count=gc,
            current_reservation_id=current_reservation_id,
        )
        serializer = self.get_serializer(tables, many=True)
        return Response(serializer.data)

    def partial_update(self, request: Request, *args: object, **kwargs: object) -> Response:
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        result_serializer = self.get_serializer(instance)
        return Response(result_serializer.data)
