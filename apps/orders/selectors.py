from apps.authentication.models import User

from .models import CartSession


def get_cart_session(session_id: str, restaurant_id: int) -> CartSession | None:
    return CartSession.objects.filter(public_id=session_id, restaurant_id=restaurant_id).first()


def is_cart_participant(user: User, session: CartSession) -> bool:
    return session.participants.filter(id=user.id).exists()
