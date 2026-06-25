import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, cast

from django.conf import settings
from django.db import IntegrityError, transaction
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.id_token import verify_oauth2_token
from rest_framework_simplejwt.tokens import RefreshToken

from .models import RoleCode, User
from .selectors import get_user_by_email, get_user_by_google_sub

logger = logging.getLogger(__name__)

_GOOGLE_OAUTH_EXCHANGE_URL = "https://oauth2.googleapis.com/token"

# Reused across verifications so id_token cert fetches share one connection pool
# instead of opening a fresh transport per login.
_google_auth_request = GoogleAuthRequest()


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
        raw = exc.read()
        try:
            body: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Google token exchange failed (status=%s): %s", exc.code, raw[:1000])
            raise ValueError("Google token exchange failed.") from exc
        logger.warning("Google token exchange failed (status=%s): %s", exc.code, body)
        raise ValueError(body.get("error_description", "Google token exchange failed.")) from exc
    except urllib.error.URLError as exc:
        logger.warning("Failed to reach Google token endpoint: %s", exc.reason)
        raise ValueError(f"Failed to reach Google: {exc.reason}") from exc


def verify_google_id_token(token: str) -> dict[str, Any]:
    try:
        claims = verify_oauth2_token(token, _google_auth_request, settings.GOOGLE_CLIENT_ID)  # type: ignore[no-untyped-call]
    except (ValueError, GoogleAuthError) as exc:
        logger.warning("Google id_token verification failed: %s", exc)
        raise ValueError("Google id_token verification failed.") from exc
    return cast(dict[str, Any], claims)


def google_authenticate(code: str, redirect_uri: str) -> User:
    token_data = exchange_google_code(code, redirect_uri)

    raw_id_token: str | None = token_data.get("id_token")
    if not raw_id_token:
        raise ValueError("No id_token in Google response.")

    claims = verify_google_id_token(raw_id_token)

    if not claims.get("email_verified"):
        raise ValueError("Google account email is not verified.")

    email: str | None = claims.get("email")
    if not email:
        raise ValueError("Google account has no email.")

    google_sub: str | None = claims.get("sub")
    if not google_sub:
        raise ValueError("Google account has no subject identifier.")

    # Match on the immutable Google sub first so an email change does not orphan
    # the account. Fall back to email only to link a pre-existing account on its
    # first Google login, then backfill the sub onto that row.
    user = get_user_by_google_sub(google_sub)
    if user is None:
        user = get_user_by_email(email)
        if user is not None:
            user.google_sub = google_sub
            user.save(update_fields=["google_sub"])
        else:
            try:
                with transaction.atomic():
                    return User.objects.create_user(
                        email=email,
                        google_sub=google_sub,
                        first_name=claims.get("given_name", ""),
                        last_name=claims.get("family_name", ""),
                        role=RoleCode.CUSTOMER,
                    )
            except IntegrityError:
                user = get_user_by_google_sub(google_sub) or get_user_by_email(email)
                if user is None:
                    raise

    if not user.is_active:
        raise ValueError("This account has been deactivated.")
    return user


def issue_tokens(user: User) -> tuple[str, str]:
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    refresh["token_version"] = user.token_version
    if user.restaurant_id is not None:
        refresh["restaurant_id"] = user.restaurant_id
    return str(refresh.access_token), str(refresh)


def issue_tokens_with_restaurant(user: User, restaurant_id: int) -> tuple[str, str]:
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    refresh["token_version"] = user.token_version
    refresh["restaurant_id"] = restaurant_id
    return str(refresh.access_token), str(refresh)


__all__ = [
    "exchange_google_code",
    "google_authenticate",
    "issue_tokens",
    "issue_tokens_with_restaurant",
]
