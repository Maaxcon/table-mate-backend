from .models import User


def get_user_by_email(email: str) -> User | None:
    return User.objects.filter(email=email).first()


__all__ = ["get_user_by_email"]
