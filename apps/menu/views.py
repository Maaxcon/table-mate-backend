from typing import Any

from django.db import transaction
from django.db.models import Count, Model, QuerySet
from django.http import Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView

from apps.authentication.permissions import IsAdmin
from common.api import (
    PublicLookupMixin,
    PublicRestaurantQueryMixin,
    RestaurantScopedViewSetMixin,
    get_restaurant_id_from_auth,
    require_restaurant_id_from_auth,
)
from common.filters import StableOrderingFilter

from . import services
from .filters import MenuCategoryFilter, MenuItemFilter
from .models import (
    Allergen,
    AllergenTranslation,
    Ingredient,
    IngredientTranslation,
    Menu,
    MenuCategory,
    MenuCategoryTranslation,
    MenuItem,
    MenuItemAllergen,
    MenuItemIngredient,
    MenuItemLike,
    MenuItemTranslation,
    MenuTranslation,
)
from .selectors import (
    get_active_menus,
    get_categories_by_restaurant,
    get_menu_items_by_restaurant,
    search_menu_items,
)
from .serializers import (
    AdminAllergenSerializer,
    AdminIngredientSerializer,
    AdminMenuCategorySerializer,
    AdminMenuItemSerializer,
    AdminMenuSerializer,
    AllergenTranslationSerializer,
    BulkItemActionSerializer,
    IngredientTranslationSerializer,
    MenuCategorySerializer,
    MenuCategoryTranslationSerializer,
    MenuItemSerializer,
    MenuItemTranslationSerializer,
    MenuSerializer,
    MenuTranslationSerializer,
    ReorderEntrySerializer,
    ToggleMenuItemLikeRequestSerializer,
    ToggleMenuItemLikeResponseSerializer,
    UpsellSuggestionResponseSerializer,
)
from .services.localization import get_localized_content, get_restaurant_locale


def _check_translation_conflict(translation: Model, current_data: dict[str, Any] | None) -> Response | None:
    """Compare-and-swap guard.  Return a 409 Response if current_data doesn't match
    the DB, or ``None`` when the request is safe to proceed."""
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




def _reorder_view(viewset: Any, request: Request) -> Response:
    """Validate {public_id, sort_order} entries and delegate to the reorder service."""
    serializer = ReorderEntrySerializer(data=request.data, many=True)
    serializer.is_valid(raise_exception=True)
    services.reorder(viewset.get_queryset(), serializer.validated_data)
    return Response(status=status.HTTP_204_NO_CONTENT)


def _get_serializer_fields(serializer: BaseSerializer[Any]) -> Any:
    target = getattr(serializer, "child", serializer)
    return getattr(target, "fields", {})


@extend_schema(tags=["Menu"])
class MenuViewSet(
    PublicRestaurantQueryMixin,
    PublicLookupMixin,
    viewsets.ReadOnlyModelViewSet[Menu],
):
    serializer_class = MenuSerializer
    permission_classes = [AllowAny]
    ordering_fields = ["created_at", "updated_at", "name"]

    def get_queryset(self) -> QuerySet[Menu]:
        restaurant_id = self.resolve_restaurant_or_not_found()
        if restaurant_id is None:
            return Menu.objects.none()
        return get_active_menus(restaurant_id=restaurant_id)

    def _localize_queryset(self, queryset: QuerySet[Menu], lang: str) -> list[Menu]:
        items = list(queryset)
        for obj in items:
            localized = get_localized_content(obj, lang)
            if localized:
                obj._localized = localized  # type: ignore[attr-defined]
        return items

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        lang = getattr(request, "active_language", None)
        if lang:
            items = self._localize_queryset(queryset, lang)
        else:
            items = list(queryset)
        page = self.paginate_queryset(items)  # type: ignore[arg-type]
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(items, many=True)
        return Response(serializer.data)

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        lang = getattr(request, "active_language", None)
        if lang:
            localized = get_localized_content(instance, lang)
            if localized:
                instance._localized = localized  # type: ignore[attr-defined]
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


@extend_schema(tags=["Menu"])
class MenuCategoryViewSet(
    PublicRestaurantQueryMixin,
    PublicLookupMixin,
    viewsets.ReadOnlyModelViewSet[MenuCategory],
):
    serializer_class = MenuCategorySerializer
    permission_classes = [AllowAny]
    filterset_class = MenuCategoryFilter
    ordering_fields = ["created_at", "updated_at", "sort_order", "name"]

    def get_queryset(self) -> QuerySet[MenuCategory]:
        restaurant_id = self.resolve_restaurant_or_not_found()
        if restaurant_id is None:
            return MenuCategory.objects.none()
        return get_categories_by_restaurant(restaurant_id=restaurant_id)

    def _localize_queryset(self, queryset: QuerySet[MenuCategory], lang: str) -> list[MenuCategory]:
        items = list(queryset)
        for obj in items:
            localized = get_localized_content(obj, lang)
            if localized:
                obj._localized = localized  # type: ignore[attr-defined]
        return items

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        lang = getattr(request, "active_language", None)
        if lang:
            items = self._localize_queryset(queryset, lang)
        else:
            items = list(queryset)
        page = self.paginate_queryset(items)  # type: ignore[arg-type]
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(items, many=True)
        return Response(serializer.data)

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        lang = getattr(request, "active_language", None)
        if lang:
            localized = get_localized_content(instance, lang)
            if localized:
                instance._localized = localized  # type: ignore[attr-defined]
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


@extend_schema(tags=["Menu Admin"])
class AdminMenuViewSet(
    RestaurantScopedViewSetMixin[Menu],
    viewsets.ModelViewSet[Menu],
):
    permission_classes = [IsAdmin]
    queryset = Menu.objects.all()
    serializer_class = AdminMenuSerializer
    restaurant_lookup = "restaurant_id"
    ordering_fields = ["name", "created_at", "updated_at"]

    def safely_get_queryset(self, qs: QuerySet[Menu]) -> QuerySet[Menu]:
        return qs.prefetch_related("translations")

    def perform_create(self, serializer: BaseSerializer[Menu]) -> None:
        serializer.save(restaurant_id=require_restaurant_id_from_auth(self.request))

    @action(detail=True, methods=["post"], url_path="translations")
    @extend_schema(
        request=MenuTranslationSerializer,
        responses={201: MenuTranslationSerializer},
    )
    def create_translation(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = MenuTranslationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        locale = get_restaurant_locale(require_restaurant_id_from_auth(request))
        if serializer.validated_data["language_code"] == locale:
            return Response(
                {"detail": f"Cannot create a translation for the primary language ({locale})."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        menu = self.get_object()
        translation = services.create_menu_translation(
            menu_id=menu.id,
            language_code=serializer.validated_data["language_code"],
            name=serializer.validated_data["name"],
        )
        return Response(MenuTranslationSerializer(translation).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["put"], url_path="translations/(?P<lang>[^/.]+)")
    @extend_schema(
        request=MenuTranslationSerializer,
        responses={200: MenuTranslationSerializer},
    )
    def update_translation(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = kwargs.pop("lang")
        locale = get_restaurant_locale(require_restaurant_id_from_auth(request))
        if lang == locale:
            return Response(
                {"detail": f"Cannot update a translation for the primary language ({locale})."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        conflict = _check_translation_conflict(
            MenuTranslation.objects.get(menu_id=self.get_object().id, language_code=lang),
            request.data.get("current"),
        )
        if conflict:
            return conflict
        update_data = request.data.get("updated", {k: v for k, v in request.data.items() if k != "current"})
        serializer = MenuTranslationSerializer(data={"language_code": lang, **update_data})
        serializer.is_valid(raise_exception=True)
        translation = services.update_menu_translation(menu_id=self.get_object().id, **serializer.validated_data)
        return Response(MenuTranslationSerializer(translation).data)

    @update_translation.mapping.delete
    def delete_translation(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = kwargs.pop("lang")
        locale = get_restaurant_locale(require_restaurant_id_from_auth(request))
        if lang == locale:
            return Response(
                {"detail": f"Cannot delete the primary language translation ({locale})."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        services.delete_menu_translation(menu_id=self.get_object().id, language_code=lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @create_translation.mapping.get
    def list_translations(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        translations = services.get_menu_translations(menu_id=self.get_object().id)
        return Response(MenuTranslationSerializer(translations, many=True).data)


@extend_schema(tags=["Menu Admin"])
class AdminMenuCategoryViewSet(
    RestaurantScopedViewSetMixin[MenuCategory],
    viewsets.ModelViewSet[MenuCategory],
):
    permission_classes = [IsAdmin]
    queryset = MenuCategory.objects.all()
    serializer_class = AdminMenuCategorySerializer
    restaurant_lookup = "menu__restaurant_id"
    filterset_class = MenuCategoryFilter
    ordering_fields = ["sort_order", "name", "created_at", "updated_at"]

    def safely_get_queryset(self, qs: QuerySet[MenuCategory]) -> QuerySet[MenuCategory]:
        # select_related avoids an N+1 from the serializer reading menu.public_id.
        return qs.select_related("menu").prefetch_related("translations")

    def get_serializer(self, *args: object, **kwargs: object) -> BaseSerializer[MenuCategory]:
        serializer = super().get_serializer(*args, **kwargs)
        # Restrict the selectable menu to the admin's own restaurant, so an admin
        # cannot attach a category to another restaurant's menu.
        restaurant_id = get_restaurant_id_from_auth(self.request)
        fields = _get_serializer_fields(serializer)
        if "menu" in fields:
            fields["menu"].queryset = (
                Menu.objects.filter(restaurant_id=restaurant_id) if restaurant_id is not None else Menu.objects.none()
            )
        return serializer

    @extend_schema(request=ReorderEntrySerializer(many=True), responses={204: None})
    @action(detail=False, methods=["post"])
    def reorder(self, request: Request) -> Response:
        return _reorder_view(self, request)

    @action(detail=True, methods=["post"], url_path="translations")
    @extend_schema(
        request=MenuCategoryTranslationSerializer,
        responses={201: MenuCategoryTranslationSerializer},
    )
    def create_translation(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = MenuCategoryTranslationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        locale = get_restaurant_locale(require_restaurant_id_from_auth(request))
        if serializer.validated_data["language_code"] == locale:
            return Response(
                {"detail": f"Cannot create a translation for the primary language ({locale})."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        translation = services.create_category_translation(
            category_id=self.get_object().id,
            **serializer.validated_data,
        )
        return Response(MenuCategoryTranslationSerializer(translation).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["put"], url_path="translations/(?P<lang>[^/.]+)")
    @extend_schema(
        request=MenuCategoryTranslationSerializer,
        responses={200: MenuCategoryTranslationSerializer},
    )
    def update_translation(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = kwargs.pop("lang")
        locale = get_restaurant_locale(require_restaurant_id_from_auth(request))
        if lang == locale:
            return Response(
                {"detail": f"Cannot update a translation for the primary language ({locale})."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        conflict = _check_translation_conflict(
            MenuCategoryTranslation.objects.get(category_id=self.get_object().id, language_code=lang),
            request.data.get("current"),
        )
        if conflict:
            return conflict
        update_data = request.data.get("updated", {k: v for k, v in request.data.items() if k != "current"})
        serializer = MenuCategoryTranslationSerializer(data={"language_code": lang, **update_data})
        serializer.is_valid(raise_exception=True)
        translation = services.update_category_translation(category_id=self.get_object().id,
                                                           **serializer.validated_data)
        return Response(MenuCategoryTranslationSerializer(translation).data)

    @update_translation.mapping.delete
    def delete_translation(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = kwargs.pop("lang")
        locale = get_restaurant_locale(require_restaurant_id_from_auth(request))
        if lang == locale:
            return Response(
                {"detail": f"Cannot delete the primary language translation ({locale})."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        services.delete_category_translation(category_id=self.get_object().id, language_code=lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @create_translation.mapping.get
    def list_translations(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        translations = services.get_category_translations(category_id=self.get_object().id)
        return Response(MenuCategoryTranslationSerializer(translations, many=True).data)


@extend_schema(tags=["Menu Admin"])
class AdminMenuItemViewSet(
    RestaurantScopedViewSetMixin[MenuItem],
    viewsets.ModelViewSet[MenuItem],
):
    permission_classes = [IsAdmin]
    queryset = MenuItem.objects.all()
    serializer_class = AdminMenuItemSerializer
    restaurant_lookup = "restaurant_id"
    filterset_class = MenuItemFilter
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    ordering_fields = ["sort_order", "name", "price", "created_at", "updated_at"]

    def safely_get_queryset(self, qs: QuerySet[MenuItem]) -> QuerySet[MenuItem]:
        # select_related avoids an N+1 from the serializer reading menu.public_id
        # and category.public_id per row. Expose a likes_count for the admin
        # (used by the dashboard charts). The aggregate adds a GROUP BY, so set an
        # explicit order to keep pagination stable (Django otherwise drops
        # Meta.ordering and warns).
        return (
            qs.select_related("menu", "category")
            .prefetch_related(
                "item_ingredients__ingredient__translations",
                "item_allergens__allergen__translations",
                "translations",
            )
            .annotate(likes_count=Count("likes", distinct=True))
            .order_by("menu_id", "sort_order", "id")
        )

    def get_serializer(self, *args: object, **kwargs: object) -> BaseSerializer[MenuItem]:
        serializer = super().get_serializer(*args, **kwargs)
        restaurant_id = get_restaurant_id_from_auth(self.request)
        fields = _get_serializer_fields(serializer)
        if "menu" in fields:
            fields["menu"].queryset = (
                Menu.objects.filter(restaurant_id=restaurant_id) if restaurant_id is not None else Menu.objects.none()
            )
        if "category" in fields:
            fields["category"].queryset = (
                MenuCategory.objects.filter(menu__restaurant_id=restaurant_id)
                if restaurant_id is not None
                else MenuCategory.objects.none()
            )
        return serializer

    def perform_create(self, serializer: BaseSerializer[MenuItem]) -> None:
        # Require the restaurant from auth so a token without one fails as a
        # permission error, not an IntegrityError from saving restaurant_id=None.
        serializer.save(restaurant_id=require_restaurant_id_from_auth(self.request))

    def perform_destroy(self, instance: MenuItem) -> None:
        allergen_ids = list(instance.item_allergens.values_list("allergen_id", flat=True))
        ingredient_ids = list(instance.item_ingredients.values_list("ingredient_id", flat=True))
        with transaction.atomic():
            instance.delete()
            services.prune_orphans(
                entity_model=Allergen,
                through_model=MenuItemAllergen,
                removed_ids=allergen_ids,
            )
            services.prune_orphans(
                entity_model=Ingredient,
                through_model=MenuItemIngredient,
                removed_ids=ingredient_ids,
            )

    @extend_schema(request=ReorderEntrySerializer(many=True), responses={204: None})
    @action(detail=False, methods=["post"])
    def reorder(self, request: Request) -> Response:
        return _reorder_view(self, request)

    @extend_schema(request=BulkItemActionSerializer, responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["post"])
    def bulk(self, request: Request) -> Response:
        """Hide/show, set the category of, or delete several dishes at once.
        Only items in the admin's restaurant are touched; unknown ids are ignored."""
        serializer = BulkItemActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.bulk_update_items(
            restaurant_id=require_restaurant_id_from_auth(request),
            data=serializer.validated_data,
        )
        return Response(result, status=status.HTTP_200_OK)

    @extend_schema(request=None, responses={201: AdminMenuItemSerializer})
    @action(detail=True, methods=["post"])
    def duplicate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Server-side copy of a dish, including its image file."""
        copy = services.duplicate_item(self.get_object())
        return Response(self.get_serializer(copy).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="translations")
    @extend_schema(
        request=MenuItemTranslationSerializer,
        responses={201: MenuItemTranslationSerializer},
    )
    def create_translation(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = MenuItemTranslationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        locale = get_restaurant_locale(require_restaurant_id_from_auth(request))
        if serializer.validated_data["language_code"] == locale:
            return Response(
                {"detail": f"Cannot create a translation for the primary language ({locale})."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        translation = services.create_item_translation(
            menu_item_id=self.get_object().id,
            **serializer.validated_data,
        )
        return Response(MenuItemTranslationSerializer(translation).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["put"], url_path="translations/(?P<lang>[^/.]+)")
    @extend_schema(
        request=MenuItemTranslationSerializer,
        responses={200: MenuItemTranslationSerializer},
    )
    def update_translation(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = kwargs.pop("lang")
        locale = get_restaurant_locale(require_restaurant_id_from_auth(request))
        if lang == locale:
            return Response(
                {"detail": f"Cannot update a translation for the primary language ({locale})."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        conflict = _check_translation_conflict(
            MenuItemTranslation.objects.get(menu_item_id=self.get_object().id, language_code=lang),
            request.data.get("current"),
        )
        if conflict:
            return conflict
        update_data = request.data.get("updated", {k: v for k, v in request.data.items() if k != "current"})
        serializer = MenuItemTranslationSerializer(data={"language_code": lang, **update_data})
        serializer.is_valid(raise_exception=True)
        translation = services.update_item_translation(menu_item_id=self.get_object().id, **serializer.validated_data)
        return Response(MenuItemTranslationSerializer(translation).data)

    @update_translation.mapping.delete
    def delete_translation(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = kwargs.pop("lang")
        locale = get_restaurant_locale(require_restaurant_id_from_auth(request))
        if lang == locale:
            return Response(
                {"detail": f"Cannot delete the primary language translation ({locale})."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        services.delete_item_translation(menu_item_id=self.get_object().id, language_code=lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @create_translation.mapping.get
    def list_translations(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        translations = services.get_item_translations(menu_item_id=self.get_object().id)
        return Response(MenuItemTranslationSerializer(translations, many=True).data)


@extend_schema(tags=["Menu Admin"])
class AdminAllergenViewSet(
    RestaurantScopedViewSetMixin[Allergen],
    viewsets.ModelViewSet[Allergen],
):
    permission_classes = [IsAdmin]
    queryset = Allergen.objects.all()
    serializer_class = AdminAllergenSerializer
    restaurant_lookup = "restaurant_id"

    def safely_get_queryset(self, qs: QuerySet[Allergen]) -> QuerySet[Allergen]:
        return qs.prefetch_related("translations")

    def perform_create(self, serializer: BaseSerializer[Allergen]) -> None:
        serializer.save(restaurant_id=require_restaurant_id_from_auth(self.request))

    @action(detail=True, methods=["post"], url_path="translations")
    @extend_schema(
        request=AllergenTranslationSerializer,
        responses={201: AllergenTranslationSerializer},
    )
    def create_translation(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = AllergenTranslationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        allergen = self.get_object()
        locale = get_restaurant_locale(allergen.restaurant_id)
        if serializer.validated_data["language_code"] == locale:
            return Response(
                {"detail": f"Cannot create a translation for the primary language ({locale})."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        translation = services.create_allergen_translation(
            allergen_public_id=str(allergen.public_id),
            restaurant_id=allergen.restaurant_id,
            **serializer.validated_data,
        )
        return Response(AllergenTranslationSerializer(translation).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["put"], url_path="translations/(?P<lang>[^/.]+)")
    @extend_schema(
        request=AllergenTranslationSerializer,
        responses={200: AllergenTranslationSerializer},
    )
    def update_translation(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = kwargs.pop("lang")
        allergen = self.get_object()
        locale = get_restaurant_locale(allergen.restaurant_id)
        if lang == locale:
            return Response(
                {"detail": f"Cannot update a translation for the primary language ({locale})."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        conflict = _check_translation_conflict(
            AllergenTranslation.objects.get(
                allergen__public_id=allergen.public_id,
                allergen__restaurant_id=allergen.restaurant_id,
                language_code=lang,
            ),
            request.data.get("current"),
        )
        if conflict:
            return conflict
        update_data = request.data.get("updated", {k: v for k, v in request.data.items() if k != "current"})
        serializer = AllergenTranslationSerializer(data={"language_code": lang, **update_data})
        serializer.is_valid(raise_exception=True)
        translation = services.update_allergen_translation(
            allergen_public_id=str(allergen.public_id),
            restaurant_id=allergen.restaurant_id,
            **serializer.validated_data,
        )
        return Response(AllergenTranslationSerializer(translation).data)

    @update_translation.mapping.delete
    def delete_translation(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = kwargs.pop("lang")
        allergen = self.get_object()
        services.delete_allergen_translation(
            allergen_public_id=str(allergen.public_id),
            restaurant_id=allergen.restaurant_id,
            language_code=lang,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @create_translation.mapping.get
    def list_translations(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        allergen = self.get_object()
        translations = services.get_allergen_translations(
            allergen_public_id=str(allergen.public_id),
            restaurant_id=allergen.restaurant_id,
        )
        return Response(AllergenTranslationSerializer(translations, many=True).data)


@extend_schema(tags=["Menu Admin"])
class AdminIngredientViewSet(
    RestaurantScopedViewSetMixin[Ingredient],
    viewsets.ModelViewSet[Ingredient],
):
    permission_classes = [IsAdmin]
    queryset = Ingredient.objects.all()
    serializer_class = AdminIngredientSerializer
    restaurant_lookup = "restaurant_id"

    def safely_get_queryset(self, qs: QuerySet[Ingredient]) -> QuerySet[Ingredient]:
        return qs.prefetch_related("translations")

    @action(detail=True, methods=["post"], url_path="translations")
    @extend_schema(
        request=IngredientTranslationSerializer,
        responses={201: IngredientTranslationSerializer},
    )
    def create_translation(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = IngredientTranslationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ingredient = self.get_object()
        locale = get_restaurant_locale(ingredient.restaurant_id)
        if serializer.validated_data["language_code"] == locale:
            return Response(
                {"detail": f"Cannot create a translation for the primary language ({locale})."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        translation = services.create_ingredient_translation(
            ingredient_id=ingredient.id,
            **serializer.validated_data,
        )
        return Response(IngredientTranslationSerializer(translation).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["put"], url_path="translations/(?P<lang>[^/.]+)")
    @extend_schema(
        request=IngredientTranslationSerializer,
        responses={200: IngredientTranslationSerializer},
    )
    def update_translation(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = kwargs.pop("lang")
        ingredient = self.get_object()
        locale = get_restaurant_locale(ingredient.restaurant_id)
        if lang == locale:
            return Response(
                {"detail": f"Cannot update a translation for the primary language ({locale})."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        conflict = _check_translation_conflict(
            IngredientTranslation.objects.get(ingredient_id=ingredient.id, language_code=lang),
            request.data.get("current"),
        )
        if conflict:
            return conflict
        update_data = request.data.get("updated", {k: v for k, v in request.data.items() if k != "current"})
        serializer = IngredientTranslationSerializer(data={"language_code": lang, **update_data})
        serializer.is_valid(raise_exception=True)
        translation = services.update_ingredient_translation(
            ingredient_id=ingredient.id,
            **serializer.validated_data,
        )
        return Response(IngredientTranslationSerializer(translation).data)

    @update_translation.mapping.delete
    def delete_translation(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = kwargs.pop("lang")
        services.delete_ingredient_translation(ingredient_id=self.get_object().id, language_code=lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @create_translation.mapping.get
    def list_translations(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        translations = services.get_ingredient_translations(ingredient_id=self.get_object().id)
        return Response(IngredientTranslationSerializer(translations, many=True).data)


@extend_schema(tags=["Menu"])
class MenuItemViewSet(
    PublicRestaurantQueryMixin,
    PublicLookupMixin,
    viewsets.ReadOnlyModelViewSet[MenuItem],
):
    serializer_class = MenuItemSerializer
    permission_classes = [AllowAny]
    filterset_class = MenuItemFilter
    ordering_fields = ["created_at", "updated_at", "sort_order", "name", "price"]

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def get_queryset(self) -> QuerySet[MenuItem]:
        restaurant_id = self.resolve_restaurant_or_not_found()
        if restaurant_id is None:
            return MenuItem.objects.none()
        guest_token = self.request.query_params.get("guest_token")
        return get_menu_items_by_restaurant(restaurant_id=restaurant_id, guest_token=guest_token)

    @action(detail=False, methods=["get"])
    @extend_schema(
        summary="Full-text search across menu items",
        parameters=[
            OpenApiParameter(name="q", description="Search query", required=True, type=str),
            OpenApiParameter(
                name="restaurant",
                description="Restaurant public UUID",
                required=True,
                type=str,
            ),
            OpenApiParameter(
                name="guest_token",
                description="Anonymous client token for personalized like state.",
                required=False,
                type=str,
            ),
        ],
    )
    def search(self, request: Request) -> Response:
        query = request.query_params.get("q", "").strip()
        restaurant_id = self.resolve_restaurant_or_not_found()
        if not query or restaurant_id is None:
            page = self.paginate_queryset(MenuItem.objects.none())
            if page is not None:
                return self.get_paginated_response([])
            return Response([])
        guest_token = request.query_params.get("guest_token")
        items = search_menu_items(
            query=query,
            restaurant_id=restaurant_id,
            guest_token=guest_token,
        )
        # Honour ?ordering= (e.g. price) just like the list endpoint; without it
        # the relevance order from search_menu_items is kept.
        items = StableOrderingFilter().filter_queryset(request, items, self)
        page = self.paginate_queryset(items)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(items, many=True).data)

    @extend_schema(
        summary="Toggle like on a menu item for an anonymous client token",
        request=ToggleMenuItemLikeRequestSerializer,
        responses={status.HTTP_200_OK: ToggleMenuItemLikeResponseSerializer},
        parameters=[
            OpenApiParameter(
                name="restaurant",
                description="Restaurant public UUID",
                required=True,
                type=OpenApiTypes.UUID,
            ),
        ],
    )
    @action(detail=True, methods=["post"], url_path="toggle-like")
    def toggle_like(self, request: Request, *args: object, **kwargs: object) -> Response:
        serializer = ToggleMenuItemLikeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        guest_token = str(serializer.validated_data["guest_token"])

        item = self.get_object()
        with transaction.atomic():
            # Lock the MenuItem row to serialize concurrent toggles for the same item.
            # Without this, two simultaneous requests can both find no like, both INSERT,
            # causing IntegrityError → get_or_create retry finds the row → deletes it,
            # leaving the item unliked even though both requests intended to like it.
            locked_item = MenuItem.objects.select_for_update().get(pk=item.pk)

            existing = MenuItemLike.objects.filter(
                menu_item=locked_item,
                guest_token=guest_token,
            ).first()

            if existing:
                existing.delete()
                is_liked = False
            else:
                MenuItemLike.objects.create(
                    menu_item=locked_item,
                    guest_token=guest_token,
                    restaurant=locked_item.restaurant,
                )
                is_liked = True

            likes_count = MenuItemLike.objects.filter(menu_item=locked_item).count()
        response_serializer = ToggleMenuItemLikeResponseSerializer(
            data={
                "public_id": item.public_id,
                "is_liked": is_liked,
                "likes_count": likes_count,
            }
        )
        response_serializer.is_valid(raise_exception=True)
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Smart upsell suggestions for a dish",
        description="Complementary items (add-ons, pairings, desserts, drinks) for the dish, "
        "ranked by co-occurrence in completed orders with a category-aware fallback.",
        parameters=[
            OpenApiParameter(
                name="restaurant",
                description="Restaurant public UUID",
                required=True,
                type=OpenApiTypes.UUID,
            ),
            OpenApiParameter(
                name="guest_token",
                description="Anonymous client token for personalized like state.",
                required=False,
                type=str,
            ),
        ],
        responses={status.HTTP_200_OK: UpsellSuggestionResponseSerializer},
    )
    @action(detail=True, methods=["get"], url_path="upsells")
    def upsells(self, request: Request, *args: object, **kwargs: object) -> Response:
        item = self.get_object()
        if not item.is_available:
            raise Http404("Menu item not found.")
        guest_token = request.query_params.get("guest_token")
        suggestions = services.get_upsells_for_item(
            restaurant_id=item.restaurant_id,
            item=item,
            guest_token=guest_token,
        )
        response_serializer = UpsellSuggestionResponseSerializer(
            instance={"count": len(suggestions), "results": suggestions},
            context=self.get_serializer_context(),
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Menu"],
    responses={200: serializers.ListSerializer(child=serializers.DictField())},
    parameters=[
        OpenApiParameter(
            name="restaurant",
            description="Restaurant public UUID",
            required=True,
            type=str,
        ),
    ],
)
class AllergenListView(APIView):
    """Allergen vocabulary for a restaurant, localized to the active language."""

    permission_classes = [AllowAny]
    serializer_class = None

    def get(self, request: Request) -> Response:
        from django.http import Http404

        from apps.restaurants.models import Restaurant

        public_id = request.query_params.get("restaurant")
        if not public_id:
            raise Http404("restaurant query param is required")
        try:
            restaurant_id: int = Restaurant.objects.values_list("id", flat=True).get(public_id=public_id)
        except Restaurant.DoesNotExist:
            raise Http404("Restaurant not found.") from None
        lang = getattr(request, "active_language", "uk")
        allergens = (
            Allergen.objects.filter(restaurant_id=restaurant_id)
            .prefetch_related("translations")
            .order_by("sort_order")
        )
        result = []
        for a in allergens:
            by_code = {t.language_code: t.name for t in a.translations.all()}
            name = by_code.get(lang, a.name)
            result.append({"public_id": str(a.public_id), "name": name})
        return Response(result)


@extend_schema(
    tags=["Menu"],
    parameters=[
        OpenApiParameter(
            name="restaurant",
            description="Restaurant public UUID",
            required=True,
            type=str,
        ),
    ],
)
class IngredientListView(APIView):
    """Ingredient vocabulary for a restaurant, localized to the active language."""

    permission_classes = [AllowAny]
    serializer_class = None

    def get(self, request: Request) -> Response:
        from django.http import Http404

        from apps.restaurants.models import Restaurant

        from .models import Ingredient

        public_id = request.query_params.get("restaurant")
        if not public_id:
            raise Http404("restaurant query param is required")
        try:
            restaurant_id: int = Restaurant.objects.values_list("id", flat=True).get(public_id=public_id)
        except Restaurant.DoesNotExist:
            raise Http404("Restaurant not found.") from None
        lang = getattr(request, "active_language", "uk")
        ingredients = (
            Ingredient.objects.filter(restaurant_id=restaurant_id)
            .prefetch_related("translations")
            .order_by("sort_order")
        )
        result = []
        for ing in ingredients:
            by_code = {t.language_code: t.name for t in ing.translations.all()}
            name = by_code.get(lang, ing.name)
            result.append({"public_id": str(ing.public_id), "name": name})
        return Response(result)
