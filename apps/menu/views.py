from django.db import transaction
from django.db.models import QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from common.api import PublicLookupMixin, PublicRestaurantQueryMixin

from .filters import MenuCategoryFilter, MenuItemFilter
from .models import Menu, MenuCategory, MenuItem, MenuItemLike
from .selectors import (
    get_active_menus,
    get_categories_by_restaurant,
    get_menu_items_by_restaurant,
    search_menu_items,
)
from .serializers import (
    MenuCategorySerializer,
    MenuItemSerializer,
    MenuSerializer,
    ToggleMenuItemLikeRequestSerializer,
    ToggleMenuItemLikeResponseSerializer,
)


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
        page = self.paginate_queryset(items)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(items, many=True).data)

    @action(detail=True, methods=["post"], url_path="toggle-like")
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
    def toggle_like(self, request: Request, *args: object, **kwargs: object) -> Response:
        serializer = ToggleMenuItemLikeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        guest_token = str(serializer.validated_data["guest_token"])

        item = self.get_object()
        with transaction.atomic():
            like, created = MenuItemLike.objects.get_or_create(
                menu_item=item,
                guest_token=guest_token,
                defaults={"restaurant": item.restaurant},
            )
            if not created:
                like.delete()
            is_liked = created

        likes_count = MenuItemLike.objects.filter(menu_item=item).count()
        response_serializer = ToggleMenuItemLikeResponseSerializer(
            data={
                "public_id": item.public_id,
                "is_liked": is_liked,
                "likes_count": likes_count,
            }
        )
        response_serializer.is_valid(raise_exception=True)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
