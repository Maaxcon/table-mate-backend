from typing import Any, cast

from django.db.models import Q, QuerySet
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.views import APIView

from apps.authentication.authentication import GuestJWTAuthentication
from apps.authentication.models import User
from apps.orders.billing import checkout_cart_session
from apps.orders.models import CartItem, CartSession, GuestProfile
from apps.orders.permissions import IsActiveTableGuest
from apps.orders.selectors import get_cart_session, is_cart_participant
from apps.orders.services import (
    add_item_to_cart,
    create_cart_session,
    get_bill_order_items,
    pay_order_items,
    remove_item_from_cart,
    update_cart_item_quantity,
)
from common.api import RestaurantScopedViewSetMixin, get_restaurant_id_from_auth
from common.exceptions import CartChangedError, CartSessionNotFoundError, DomainError

from .serializers import (
    AddCartItemSerializer,
    BillItemSerializer,
    CartItemSerializer,
    CartSessionSerializer,
    CheckoutResponseSerializer,
    PayOrderItemsSerializer,
    SetGuestNameSerializer,
    UpdateCartItemSerializer,
)


class GuestFallbackAuthMixin:
    def perform_authentication(self, request: Request) -> None:
        try:
            super().perform_authentication(request)  # type: ignore[misc]
        except AuthenticationFailed:
            guest = GuestJWTAuthentication()
            result = guest.authenticate(request)
            if result is not None:
                request.user, request.auth = result
            else:
                raise


def _is_guest_request(request: Request) -> bool:
    auth = getattr(request, "auth", None)
    if auth is not None:
        payload = getattr(auth, "payload", {})
        return bool(payload.get("is_guest"))
    return False


def _get_guest_identity_from_request(request: Request) -> str | None:
    auth = getattr(request, "auth", None)
    if auth is not None:
        payload = getattr(auth, "payload", {})
        if payload.get("is_guest"):
            return payload.get("guest_id")
    return None


_MAX_CLIENT_ID_LENGTH = 64


def _get_client_id_from_request(request: Request) -> str | None:
    client_id = request.headers.get("X-Client-Id")
    if not client_id:
        return None
    return client_id[:_MAX_CLIENT_ID_LENGTH]


@extend_schema(tags=["Cart"])
class CartSessionViewSet(
    GuestFallbackAuthMixin,
    RestaurantScopedViewSetMixin[CartSession],
    viewsets.ModelViewSet[CartSession],
):
    permission_classes = [IsActiveTableGuest]
    serializer_class = CartSessionSerializer
    http_method_names = ["get", "post", "head", "options"]
    queryset = CartSession.objects.all()
    lookup_url_kwarg = "pk"  # type: ignore[misc]

    def safely_get_queryset(self, qs: QuerySet[CartSession]) -> QuerySet[CartSession]:
        if _is_guest_request(self.request):
            auth = getattr(self.request, "auth", None)
            payload = getattr(auth, "payload", {})
            session_id = payload.get("cart_session_id")
            if session_id:
                return qs.filter(public_id=session_id)
            return qs.none()
        user = cast(User, self.request.user)
        return (
            qs.filter(Q(participants=user) | Q(reservation__participants=user) | Q(reservation__customer=user))
            .prefetch_related("participants")
            .distinct()
        )

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
    GuestFallbackAuthMixin,
    RestaurantScopedViewSetMixin[CartItem],
    viewsets.ModelViewSet[CartItem],
):
    throttle_scope = "cart"
    permission_classes = [IsActiveTableGuest]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    queryset = CartItem.objects.all()
    lookup_url_kwarg = "pk"  # type: ignore[misc]

    def get_serializer_context(self) -> dict[str, object]:
        ctx = dict(super().get_serializer_context())
        session_pk = self.kwargs.get("session_pk")
        if session_pk is not None:
            ctx["guest_profiles"] = dict(
                GuestProfile.objects.filter(cart_session__public_id=session_pk).values_list(
                    "guest_identity", "display_name"
                )
            )
        return ctx

    def get_serializer_class(self) -> type[Serializer[Any]]:
        if self.action == "create":
            return AddCartItemSerializer
        if self.action == "partial_update":
            return UpdateCartItemSerializer
        return CartItemSerializer

    def safely_get_queryset(self, qs: QuerySet[CartItem]) -> QuerySet[CartItem]:
        session_pk = self.kwargs.get("session_pk")
        if _is_guest_request(self.request):
            qs = qs.filter(cart_session__public_id=session_pk) if session_pk else qs
        else:
            user = cast(User, self.request.user)
            qs = qs.filter(
                Q(cart_session__participants=user)
                | Q(cart_session__reservation__participants=user)
                | Q(cart_session__reservation__customer=user)
            )
            if session_pk:
                qs = qs.filter(cart_session__public_id=session_pk)
        return qs.select_related("menu_item", "cart_session").distinct()

    def _get_restaurant_id(self) -> int:
        rid = get_restaurant_id_from_auth(self.request)
        if rid is None:
            raise DomainError("Restaurant context required.")
        return rid

    def _get_session(self) -> CartSession:
        session_pk = self.kwargs["session_pk"]
        if _is_guest_request(self.request):
            auth = getattr(self.request, "auth", None)
            payload = getattr(auth, "payload", {})
            token_session_id = payload.get("cart_session_id")
            if token_session_id and str(token_session_id) != str(session_pk):
                raise PermissionDenied("Guest token is not scoped to this session.")
            session = CartSession.objects.filter(public_id=session_pk).first()
        else:
            restaurant_id = self._get_restaurant_id()
            session = get_cart_session(restaurant_id=restaurant_id, session_pk=str(session_pk))
        if session is None:
            raise CartSessionNotFoundError(f"Cart session {session_pk} not found.")
        return session

    def _get_user_or_anon(self) -> User | None:
        user = self.request.user
        if user is None or user.is_anonymous:
            return None
        return user

    @extend_schema(responses={201: CartItemSerializer})
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session = self._get_session()

        item = add_item_to_cart(
            session=session,
            menu_item_id=str(serializer.validated_data["menu_item"].public_id),
            quantity=serializer.validated_data["quantity"],
            user=self._get_user_or_anon(),
            guest_identity=_get_guest_identity_from_request(request),
            guest_slot=serializer.validated_data.get("guest_slot"),
            comment=serializer.validated_data.get("comment"),
            client_id=_get_client_id_from_request(request),
        )

        result = CartItemSerializer(item, context=self.get_serializer_context())

        return Response(result.data, status=status.HTTP_201_CREATED)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        session = self._get_session()

        remove_item_from_cart(
            session=session,
            item_id=self.kwargs["pk"],
            user=self._get_user_or_anon(),
            client_id=_get_client_id_from_request(request),
        )

        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=UpdateCartItemSerializer,
        responses={200: CartItemSerializer},
    )
    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session = self._get_session()

        kwargs = cast(
            dict[str, Any],
            {
                "session": session,
                "item_id": self.kwargs["pk"],
                "quantity": serializer.validated_data["quantity"],
                "user": self._get_user_or_anon(),
                "client_id": _get_client_id_from_request(request),
            },
        )
        if "comment" in serializer.validated_data:
            kwargs["comment"] = serializer.validated_data["comment"]
        if "guest_slot" in serializer.validated_data:
            kwargs["guest_slot"] = serializer.validated_data["guest_slot"]
        item = update_cart_item_quantity(**kwargs)

        result = CartItemSerializer(item, context=self.get_serializer_context())

        return Response(result.data, status=status.HTTP_200_OK)


def _request_user_or_none(request: Request) -> User | None:
    user = request.user
    if user is None or user.is_anonymous:
        return None
    return user


def _resolve_checkout_session(request: Request, session_pk: str) -> CartSession:
    if _is_guest_request(request):
        # IsActiveTableGuest already verified the token is scoped to session_pk.
        session = CartSession.objects.filter(public_id=session_pk).first()
    else:
        restaurant_id = get_restaurant_id_from_auth(request)
        session = (
            get_cart_session(restaurant_id=restaurant_id, session_pk=str(session_pk))
            if restaurant_id is not None
            else None
        )
        if session is not None:
            user = _request_user_or_none(request)
            if user is None or not is_cart_participant(user, session):
                raise PermissionDenied("Only cart participants may check out this cart.")
    if session is None:
        raise CartSessionNotFoundError(f"Cart session {session_pk} not found.")
    return session


@extend_schema(tags=["Cart"])
class CartCheckoutView(GuestFallbackAuthMixin, APIView):
    throttle_scope = "checkout"
    permission_classes = [IsActiveTableGuest]
    serializer_class = None

    @extend_schema(
        request=None,
        responses={
            201: CheckoutResponseSerializer,
            400: OpenApiResponse(description="Cart is empty."),
            409: OpenApiResponse(description="Cart changed: unavailable items were removed (code CART_CHANGED)."),
        },
    )
    def post(self, request: Request, session_pk: str) -> Response:
        session = _resolve_checkout_session(request, session_pk)
        try:
            order = checkout_cart_session(cart_session=session, user=_request_user_or_none(request))
        except CartChangedError as exc:
            return Response(
                {"detail": exc.default_detail, "code": exc.default_code, "removed": exc.removed},
                status=status.HTTP_409_CONFLICT,
            )
        # Goods subtotal isn't stored on Order; derive it so the receipt
        # reconciles: total = subtotal + tax + service_charge.
        subtotal = order.total_amount - order.tax_total - order.service_charge
        return Response(
            {
                "order_id": str(order.public_id),
                "subtotal": str(subtotal),
                "tax": str(order.tax_total),
                "service_charge": str(order.service_charge),
                "total": str(order.total_amount),
                "currency": order.currency,
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Cart"])
@extend_schema(tags=["Cart"])
class SetGuestNameView(GuestFallbackAuthMixin, APIView):
    permission_classes = [IsActiveTableGuest]

    @extend_schema(
        request=SetGuestNameSerializer,
        responses={200: None},
    )
    def post(self, request: Request, session_pk: str) -> Response:
        serializer = SetGuestNameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        guest_identity = _get_guest_identity_from_request(request)
        if not guest_identity:
            return Response(
                {"detail": "Guest identity required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = CartSession.objects.filter(public_id=session_pk).first()
        if session is None:
            return Response(
                {"detail": "Cart session not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        GuestProfile.objects.update_or_create(
            cart_session=session,
            guest_identity=guest_identity,
            defaults={
                "display_name": serializer.validated_data["display_name"],
                "restaurant_id": session.restaurant_id,
            },
        )

        return Response(status=status.HTTP_200_OK)


@extend_schema(tags=["Cart"])
class CartBillView(GuestFallbackAuthMixin, APIView):
    """Ordered (already-submitted) items for this table's visit — the bill."""

    throttle_scope = "checkout"
    permission_classes = [IsActiveTableGuest]
    serializer_class = BillItemSerializer

    @extend_schema(responses={200: BillItemSerializer(many=True)})
    def get(self, request: Request, session_pk: str) -> Response:
        session = _resolve_checkout_session(request, session_pk)
        items = get_bill_order_items(cart_session=session)
        return Response(BillItemSerializer(items, many=True).data, status=status.HTTP_200_OK)


@extend_schema(tags=["Cart"])
class CartPayView(GuestFallbackAuthMixin, APIView):
    """Mark selected ordered items as paid (simulated). Returns the updated bill."""

    throttle_scope = "checkout"
    permission_classes = [IsActiveTableGuest]
    serializer_class = PayOrderItemsSerializer

    @extend_schema(
        request=PayOrderItemsSerializer,
        responses={200: BillItemSerializer(many=True)},
    )
    def post(self, request: Request, session_pk: str) -> Response:
        serializer = PayOrderItemsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = _resolve_checkout_session(request, session_pk)
        items = pay_order_items(
            cart_session=session,
            order_item_ids=[str(i) for i in serializer.validated_data["order_item_ids"]],
            client_id=_get_client_id_from_request(request),
        )
        return Response(BillItemSerializer(items, many=True).data, status=status.HTTP_200_OK)
