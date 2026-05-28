from django.db.models import QuerySet

from apps.authentication.models import User

from .models import CartItem, CartSession


def get_cart_session(session_id: str, restaurant_id: int) -> CartSession | None:
    return CartSession.objects.filter(public_id=session_id, restaurant_id=restaurant_id).first()


def get_cart_items(session_id: str, restaurant_id: int) -> QuerySet[CartItem]:
    return CartItem.objects.filter(
        cart_session__public_id=session_id,
        restaurant_id=restaurant_id,
    ).select_related("menu_item", "added_by")


def is_cart_participant(user: User, session: CartSession) -> bool:
    return session.participants.filter(id=user.id).exists()


def get_cart_sessions_for_reservation(reservation_id: str, restaurant_id: int) -> QuerySet[CartSession]:
    return CartSession.objects.filter(
        reservation__public_id=reservation_id,
        restaurant_id=restaurant_id,
    )


def get_cart_sessions_for_user(user: User, restaurant_id: int) -> QuerySet[CartSession]:
    return CartSession.objects.filter(
        participants=user,
        restaurant_id=restaurant_id,
    )
