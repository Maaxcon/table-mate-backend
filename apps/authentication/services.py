import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, cast

from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken

from .models import RoleCode, User
from .selectors import get_user_by_email

_GOOGLE_OAUTH_EXCHANGE_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def exchange_google_code(code: str, redirect_uri: str) -> dict[str, Any]:
    payload = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode()
    req = urllib.request.Request(_GOOGLE_OAUTH_EXCHANGE_URL, data=payload, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
            return cast(dict[str, Any], json.loads(resp.read()))
    except urllib.error.HTTPError as exc:
        try:
            body: dict[str, Any] = json.loads(exc.read())
        except json.JSONDecodeError:
            raise ValueError("Google token exchange failed.") from exc
        raise ValueError(body.get("error_description", "Google token exchange failed.")) from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Failed to reach Google: {exc.reason}") from exc


def fetch_google_userinfo(access_token: str) -> dict[str, Any]:
    req = urllib.request.Request(
        _GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
            return cast(dict[str, Any], json.loads(resp.read()))
    except urllib.error.URLError as exc:
        raise ValueError(f"Failed to reach Google: {exc.reason}") from exc


def google_authenticate(code: str, redirect_uri: str) -> User:
    token_data = exchange_google_code(code, redirect_uri)

    google_access_token: str | None = token_data.get("access_token")
    if not google_access_token:
        raise ValueError("No access token in Google response.")

    userinfo = fetch_google_userinfo(google_access_token)

    if not userinfo.get("email_verified"):
        raise ValueError("Google account email is not verified.")

    email: str | None = userinfo.get("email")
    if not email:
        raise ValueError("Google account has no email.")

    user = get_user_by_email(email)
    if user is None:
        user = User.objects.create_user(
            email=email,
            first_name=userinfo.get("given_name", ""),
            last_name=userinfo.get("family_name", ""),
            role=RoleCode.CUSTOMER,
        )
    elif not user.is_active:
        raise ValueError("This account has been deactivated.")
    return user


def issue_tokens(user: User) -> tuple[str, str]:
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    refresh["token_version"] = user.token_version
    return str(refresh.access_token), str(refresh)


def issue_tokens_with_restaurant(user: User, restaurant_id: int) -> tuple[str, str]:
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    refresh["token_version"] = user.token_version
    refresh["restaurant_id"] = restaurant_id
    return str(refresh.access_token), str(refresh)


__all__ = [
    "exchange_google_code",
    "fetch_google_userinfo",
    "google_authenticate",
    "issue_tokens",
    "issue_tokens_with_restaurant",
]
