from typing import Any, cast

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer

from apps.authentication.models import User
from apps.orders.models import CartItem, CartSession
from apps.orders.selectors import get_cart_session
from apps.orders.services import add_item_to_cart, create_cart_session, remove_item_from_cart
from common.api import RestaurantScopedViewSetMixin, get_restaurant_id_from_auth
from common.exceptions import CartSessionNotFoundError, DomainError

from .serializers import AddCartItemSerializer, CartItemSerializer, CartSessionSerializer


@extend_schema(tags=["Cart"])
class CartSessionViewSet(
    RestaurantScopedViewSetMixin[CartSession],
    viewsets.ModelViewSet[CartSession],
):
    permission_classes = [IsAuthenticated]
    serializer_class = CartSessionSerializer
    http_method_names = ["get", "post", "head", "options"]
    queryset = CartSession.objects.all()
    lookup_url_kwarg = "pk"  # type: ignore[misc]

    def safely_get_queryset(self, qs: QuerySet[CartSession]) -> QuerySet[CartSession]:
        user = cast(User, self.request.user)
        return qs.filter(participants=user).prefetch_related("participants")

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        restaurant_id = get_restaurant_id_from_auth(request)
        if restaurant_id is None:
            return Response(
                {"detail": "Restaurant context required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = cast(User, request.user)
        session = create_cart_session(
            restaurant_id=restaurant_id,
            reservation_id=str(serializer.validated_data["reservation"].public_id),
            user=user,
        )

        result = self.get_serializer(session)
        return Response(result.data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Cart"])
class CartSessionItemViewSet(
    RestaurantScopedViewSetMixin[CartItem],
    viewsets.ModelViewSet[CartItem],
):
    queryset = CartItem.objects.all()
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_serializer_class(self) -> type[Serializer[Any]]:
        if self.action == "create":
            return AddCartItemSerializer
        return CartItemSerializer

    def safely_get_queryset(self, qs: QuerySet[CartItem]) -> QuerySet[CartItem]:
        user = cast(User, self.request.user)
        qs = qs.filter(cart_session__participants=user)
        session_pk = self.kwargs.get("session_pk")
        if session_pk:
            qs = qs.filter(cart_session__public_id=session_pk)
        return qs.select_related("menu_item", "cart_session")

    def _get_restaurant_id(self) -> int:
        rid = get_restaurant_id_from_auth(self.request)
        if rid is None:
            raise DomainError("Restaurant context required.")
        return rid

    def _get_session(self) -> CartSession:
        session_pk = cast(str, self.kwargs["session_pk"])
        restaurant_id = self._get_restaurant_id()
        session = get_cart_session(restaurant_id=restaurant_id, session_pk=session_pk)
        if session is None:
            raise CartSessionNotFoundError(f"Cart session {session_pk} not found.")
        return session

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session = self._get_session()

        user = cast(User, request.user)
        item = add_item_to_cart(
            session=session,
            menu_item_id=str(serializer.validated_data["menu_item"].public_id),
            quantity=serializer.validated_data["quantity"],
            user=user,
            comment=serializer.validated_data.get("comment"),
        )
        item = CartItem.objects.select_related("menu_item", "cart_session").get(pk=item.pk)
        result = CartItemSerializer(item, context=self.get_serializer_context())
        return Response(result.data, status=status.HTTP_201_CREATED)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        session = self._get_session()

        user = cast(User, request.user)
        remove_item_from_cart(
            session=session,
            item_id=self.kwargs["pk"],
            user=user,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
