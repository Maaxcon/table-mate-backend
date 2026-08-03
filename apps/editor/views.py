from datetime import datetime
from typing import Any
from uuid import UUID

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
from apps.restaurants.models import Restaurant, RestaurantSettings, Table
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

from .models import Layout, LayoutDraft, LayoutEntityTranslation, LayoutVersion
from .selectors import get_available_tables
from .serializers import (
    DraftLayoutSerializer,
    EditorTableSerializer,
    LayoutEntityTranslationSerializer,
    LayoutSerializer,
    LayoutVersionSerializer,
    PublishLayoutSerializer,
)
from .services import (
    LayoutVersionConflictError,
    TableInUseError,
    create_layout_entity_translation,
    delete_draft,
    delete_layout_entity_translation,
    get_layout_entity_translations,
    localize_layout_json,
    publish_layout,
    save_draft,
    update_layout_entity_translation,
)


def _check_translation_conflict(
    translation: LayoutEntityTranslation, current_data: dict[str, Any] | None
) -> Response | None:
    """Compare-and-swap guard matching the menu/zone/table translation endpoints.

    Return a 409 Response when ``current_data`` doesn't match the DB, or ``None``
    when the request is safe to proceed.
    """
    if not current_data:
        return None
    conflicts = {}
    for field, expected in current_data.items():
        actual = getattr(translation, field)
        if actual != expected:
            conflicts[field] = actual
    if not conflicts:
        return None
    return Response(
        {
            "detail": "CONFLICT: Translation was modified. Please refresh and try again.",
            "current": conflicts,
        },
        status=status.HTTP_409_CONFLICT,
    )


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

        latest = self._latest_version(restaurant_id)
        if latest is None:
            return Response({"layout_json": None, "layout_version_id": None})

        layout_json = latest.layout_json
        lang = getattr(request, "active_language", None)
        if lang:
            layout_json = localize_layout_json(layout_json, lang, latest.pk)
        return Response(
            {
                "layout_json": layout_json,
                "layout_version_id": str(latest.public_id),
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

    # ── Floor plan entity translations (FR-027..FR-033) ─────────────

    def _latest_version(self, restaurant_id: int) -> LayoutVersion | None:
        return (
            LayoutVersion.objects.filter(restaurant_id=restaurant_id)
            .order_by("-published_at", "-id")
            .first()
        )

    def _entity_exists_in_latest(self, version: LayoutVersion, entity_id: str) -> bool:
        for entity_type in ("thresholds", "portals"):
            for entity in version.layout_json.get(entity_type, []):
                if str(entity.get("id")) == entity_id:
                    return True
        return False

    def _default_language_for(self, restaurant_id: int) -> str | None:
        settings = (
            RestaurantSettings.objects.filter(restaurant_id=restaurant_id)
            .values_list("locale", flat=True)
            .first()
        )
        return settings

    def _reject_default_language(self, restaurant_id: int, language_code: str) -> Response | None:
        if self._default_language_for(restaurant_id) == language_code:
            return Response(
                {"detail": "Cannot translate the restaurant's primary language."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return None

    def _parse_entity_id(self, raw: str) -> Response | str:
        try:
            return str(UUID(raw))
        except ValueError:
            return Response(
                {"detail": "Invalid entity id."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @extend_schema(
        methods=["GET"],
        summary="List floor plan entity translations",
        description=(
            "Returns label translations for thresholds/portals in the latest published layout. "
            "Table labels are managed via TableTranslation and not included here."
        ),
        parameters=[
            OpenApiParameter(
                name="language",
                type=str,
                required=False,
                description="Filter translations to a single language code.",
            ),
        ],
        responses=LayoutEntityTranslationSerializer(many=True),
    )
    @extend_schema(
        methods=["POST"],
        summary="Create a floor plan entity translation",
        description="Stores a label translation for a threshold/portal against the latest published layout version.",
        request=LayoutEntityTranslationSerializer,
        responses={201: LayoutEntityTranslationSerializer},
    )
    @action(
        detail=False,
        methods=["get", "post"],
        url_path="entity-translations",
        permission_classes=[IsAdmin],
    )
    def entity_translations(self, request: Request) -> Response:
        if request.method == "POST":
            return self._create_entity_translation(request)
        return self._list_entity_translations(request)

    def _list_entity_translations(self, request: Request) -> Response:
        restaurant_id = require_restaurant_id_from_auth(request)
        latest = self._latest_version(restaurant_id)
        if latest is None:
            return Response([])
        translations = get_layout_entity_translations(
            layout_version_id=latest.pk,
            language_code=request.query_params.get("language"),
        )
        return Response(LayoutEntityTranslationSerializer(translations, many=True).data)

    def _create_entity_translation(self, request: Request) -> Response:
        restaurant_id = require_restaurant_id_from_auth(request)
        latest = self._latest_version(restaurant_id)
        if latest is None:
            return Response(
                {"detail": "No published layout yet."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = LayoutEntityTranslationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity_id = str(serializer.validated_data["entity_id"])
        language_code = serializer.validated_data["language_code"]

        rejected = self._reject_default_language(restaurant_id, language_code)
        if rejected is not None:
            return rejected
        if not self._entity_exists_in_latest(latest, entity_id):
            return Response(
                {"detail": "Entity does not exist in the latest published layout."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if LayoutEntityTranslation.objects.filter(
            layout_version_id=latest.pk, entity_id=entity_id, language_code=language_code
        ).exists():
            return Response(
                {"detail": "A translation for this entity and language already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        translation = create_layout_entity_translation(
            layout_version_id=latest.pk,
            entity_id=entity_id,
            language_code=language_code,
            label=serializer.validated_data["label"],
        )
        return Response(
            LayoutEntityTranslationSerializer(translation).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        methods=["PUT"],
        summary="Update a floor plan entity translation",
        description=(
            "Updates a label translation for a threshold/portal. Supports optimistic locking "
            "via ``current``/``updated`` payloads; a stale ``current`` returns 409 CONFLICT."
        ),
        request=LayoutEntityTranslationSerializer,
        responses={200: LayoutEntityTranslationSerializer},
    )
    @extend_schema(
        methods=["DELETE"],
        summary="Delete a floor plan entity translation",
        responses={204: None},
    )
    @action(
        detail=False,
        methods=["put", "delete"],
        url_path=r"entity-translations/(?P<entity_id>[^/.]+)/(?P<lang>[^/.]+)",
        permission_classes=[IsAdmin],
    )
    def entity_translation(self, request: Request, entity_id: str, lang: str) -> Response:
        if request.method == "DELETE":
            return self._delete_entity_translation(request, entity_id, lang)
        return self._update_entity_translation(request, entity_id, lang)

    def _update_entity_translation(self, request: Request, entity_id: str, lang: str) -> Response:
        restaurant_id = require_restaurant_id_from_auth(request)
        parsed = self._parse_entity_id(entity_id)
        if isinstance(parsed, Response):
            return parsed
        latest = self._latest_version(restaurant_id)
        if latest is None:
            return Response(
                {"detail": "No published layout yet."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rejected = self._reject_default_language(restaurant_id, lang)
        if rejected is not None:
            return rejected
        if not self._entity_exists_in_latest(latest, parsed):
            return Response(
                {"detail": "Entity does not exist in the latest published layout."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        translation = (
            LayoutEntityTranslation.objects.filter(
                layout_version_id=latest.pk, entity_id=parsed, language_code=lang
            ).first()
        )
        if translation is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        conflict = _check_translation_conflict(translation, request.data.get("current"))
        if conflict:
            return conflict
        update_data = request.data.get(
            "updated", {k: v for k, v in request.data.items() if k != "current"}
        )
        serializer = LayoutEntityTranslationSerializer(
            data={"entity_id": parsed, "language_code": lang, **update_data}
        )
        serializer.is_valid(raise_exception=True)
        translation = update_layout_entity_translation(
            layout_version_id=latest.pk,
            entity_id=parsed,
            language_code=lang,
            label=serializer.validated_data["label"],
        )
        return Response(LayoutEntityTranslationSerializer(translation).data)

    def _delete_entity_translation(self, request: Request, entity_id: str, lang: str) -> Response:
        restaurant_id = require_restaurant_id_from_auth(request)
        parsed = self._parse_entity_id(entity_id)
        if isinstance(parsed, Response):
            return parsed
        latest = self._latest_version(restaurant_id)
        if latest is None:
            return Response(
                {"detail": "No published layout yet."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rejected = self._reject_default_language(restaurant_id, lang)
        if rejected is not None:
            return rejected
        if not self._entity_exists_in_latest(latest, parsed):
            return Response(
                {"detail": "Entity does not exist in the latest published layout."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        delete_layout_entity_translation(
            layout_version_id=latest.pk,
            entity_id=parsed,
            language_code=lang,
        )
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
