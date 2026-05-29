from apps.authentication.models import User

from .models import CartSession


def is_cart_participant(user: User, session: CartSession) -> bool:
    return session.participants.filter(id=user.id).exists()
