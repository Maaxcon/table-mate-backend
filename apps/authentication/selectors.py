from .models import User


def get_user_by_email(email: str) -> User | None:
    return User.objects.filter(email=email.lower()).first()


def get_user_by_google_sub(google_sub: str) -> User | None:
    return User.objects.filter(google_sub=google_sub).first()


__all__ = ["get_user_by_email", "get_user_by_google_sub"]
