import json
import urllib.error
from io import BytesIO
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from django.db import IntegrityError, transaction
from google.auth.exceptions import GoogleAuthError
from rest_framework_simplejwt.tokens import AccessToken, Token

from apps.authentication.models import RoleCode, User
from apps.authentication.services import google_authenticate, issue_tokens, issue_tokens_with_restaurant
from tests.conftest import UserFactory


def _urlopen_mock(body: dict[str, Any]) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(body).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _http_error(description: str, code: int = 400) -> urllib.error.HTTPError:
    fp = BytesIO(json.dumps({"error_description": description}).encode())
    return urllib.error.HTTPError(
        url="https://oauth2.googleapis.com/token",
        code=code,
        msg="Bad Request",
        hdrs={},  # type: ignore[arg-type]
        fp=fp,
    )


@pytest.mark.django_db
class TestGoogleAuthenticate:
    def test_creates_new_user(self) -> None:
        with (
            patch("apps.authentication.services.urllib.request.urlopen") as mock_open,
            patch("apps.authentication.services.verify_oauth2_token") as mock_verify,
        ):
            mock_open.return_value = _urlopen_mock({"id_token": "jwt"})
            mock_verify.return_value = {
                "sub": "google-sub-new",
                "email": "new@example.com",
                "email_verified": True,
                "given_name": "John",
                "family_name": "Doe",
            }
            user = google_authenticate("code123", "http://localhost:3000")

        assert user.email == "new@example.com"
        assert user.google_sub == "google-sub-new"
        assert user.first_name == "John"
        assert user.last_name == "Doe"
        assert user.role == RoleCode.CUSTOMER

    def test_returns_existing_user(self) -> None:
        existing = UserFactory.create(email="existing@example.com", google_sub="google-sub-1")

        with (
            patch("apps.authentication.services.urllib.request.urlopen") as mock_open,
            patch("apps.authentication.services.verify_oauth2_token") as mock_verify,
        ):
            mock_open.return_value = _urlopen_mock({"id_token": "jwt"})
            mock_verify.return_value = {
                "sub": "google-sub-1",
                "email": "existing@example.com",
                "email_verified": True,
            }
            user = google_authenticate("code123", "http://localhost:3000")

        assert user.pk == existing.pk

    def test_matches_by_sub_when_google_email_changed(self) -> None:
        existing = UserFactory.create(email="old@example.com", google_sub="stable-sub")

        with (
            patch("apps.authentication.services.urllib.request.urlopen") as mock_open,
            patch("apps.authentication.services.verify_oauth2_token") as mock_verify,
        ):
            mock_open.return_value = _urlopen_mock({"id_token": "jwt"})
            mock_verify.return_value = {
                "sub": "stable-sub",
                "email": "new@example.com",
                "email_verified": True,
            }
            user = google_authenticate("code123", "http://localhost:3000")

        assert user.pk == existing.pk

    def test_links_and_backfills_sub_for_preexisting_email_account(self) -> None:
        existing = UserFactory.create(email="legacy@example.com", google_sub=None)

        with (
            patch("apps.authentication.services.urllib.request.urlopen") as mock_open,
            patch("apps.authentication.services.verify_oauth2_token") as mock_verify,
        ):
            mock_open.return_value = _urlopen_mock({"id_token": "jwt"})
            mock_verify.return_value = {
                "sub": "freshly-linked-sub",
                "email": "legacy@example.com",
                "email_verified": True,
            }
            user = google_authenticate("code123", "http://localhost:3000")

        existing.refresh_from_db()
        assert user.pk == existing.pk
        assert existing.google_sub == "freshly-linked-sub"

    def test_raises_when_no_sub_in_claims(self) -> None:
        with (
            patch("apps.authentication.services.urllib.request.urlopen") as mock_open,
            patch("apps.authentication.services.verify_oauth2_token") as mock_verify,
        ):
            mock_open.return_value = _urlopen_mock({"id_token": "jwt"})
            mock_verify.return_value = {"email": "x@example.com", "email_verified": True}
            with pytest.raises(ValueError, match="subject identifier"):
                google_authenticate("code123", "http://localhost:3000")

    def test_raises_on_google_exchange_error(self) -> None:
        with patch(
            "apps.authentication.services.urllib.request.urlopen",
            side_effect=_http_error("invalid_grant"),
        ):
            with pytest.raises(ValueError, match="invalid_grant"):
                google_authenticate("bad-code", "http://localhost:3000")

    def test_raises_generic_message_on_non_json_google_error(self) -> None:
        from io import BytesIO

        html_error = urllib.error.HTTPError(
            url="https://oauth2.googleapis.com/token",
            code=502,
            msg="Bad Gateway",
            hdrs={},  # type: ignore[arg-type]
            fp=BytesIO(b"<html>Bad Gateway</html>"),
        )
        with patch(
            "apps.authentication.services.urllib.request.urlopen",
            side_effect=html_error,
        ):
            with pytest.raises(ValueError, match="Google token exchange failed"):
                google_authenticate("bad-code", "http://localhost:3000")

    def test_raises_when_no_id_token_in_response(self) -> None:
        with patch("apps.authentication.services.urllib.request.urlopen") as mock_open:
            mock_open.return_value = _urlopen_mock({})
            with pytest.raises(ValueError, match="No id_token"):
                google_authenticate("code123", "http://localhost:3000")

    def test_raises_on_invalid_id_token(self) -> None:
        with (
            patch("apps.authentication.services.urllib.request.urlopen") as mock_open,
            patch(
                "apps.authentication.services.verify_oauth2_token",
                side_effect=ValueError("Token expired"),
            ),
        ):
            mock_open.return_value = _urlopen_mock({"id_token": "jwt"})
            with pytest.raises(ValueError, match="id_token verification failed"):
                google_authenticate("code123", "http://localhost:3000")

    def test_raises_on_wrong_issuer_id_token(self) -> None:
        with (
            patch("apps.authentication.services.urllib.request.urlopen") as mock_open,
            patch(
                "apps.authentication.services.verify_oauth2_token",
                side_effect=GoogleAuthError("Wrong issuer."),
            ),
        ):
            mock_open.return_value = _urlopen_mock({"id_token": "jwt"})
            with pytest.raises(ValueError, match="id_token verification failed"):
                google_authenticate("code123", "http://localhost:3000")

    def test_creates_user_with_no_given_or_family_name(self) -> None:
        with (
            patch("apps.authentication.services.urllib.request.urlopen") as mock_open,
            patch("apps.authentication.services.verify_oauth2_token") as mock_verify,
        ):
            mock_open.return_value = _urlopen_mock({"id_token": "jwt"})
            mock_verify.return_value = {"sub": "sub-noname", "email": "x@example.com", "email_verified": True}
            user = google_authenticate("code123", "http://localhost:3000")

        assert user.email == "x@example.com"
        assert user.first_name == ""
        assert user.last_name == ""

    def test_raises_when_email_not_verified(self) -> None:
        with (
            patch("apps.authentication.services.urllib.request.urlopen") as mock_open,
            patch("apps.authentication.services.verify_oauth2_token") as mock_verify,
        ):
            mock_open.return_value = _urlopen_mock({"id_token": "jwt"})
            mock_verify.return_value = {"email": "x@example.com", "email_verified": False}
            with pytest.raises(ValueError, match="not verified"):
                google_authenticate("code123", "http://localhost:3000")

    def test_raises_when_email_verified_missing(self) -> None:
        with (
            patch("apps.authentication.services.urllib.request.urlopen") as mock_open,
            patch("apps.authentication.services.verify_oauth2_token") as mock_verify,
        ):
            mock_open.return_value = _urlopen_mock({"id_token": "jwt"})
            mock_verify.return_value = {}
            with pytest.raises(ValueError, match="not verified"):
                google_authenticate("code123", "http://localhost:3000")

    def test_raises_for_inactive_account(self) -> None:
        UserFactory.create(email="inactive@example.com", is_active=False)

        with (
            patch("apps.authentication.services.urllib.request.urlopen") as mock_open,
            patch("apps.authentication.services.verify_oauth2_token") as mock_verify,
        ):
            mock_open.return_value = _urlopen_mock({"id_token": "jwt"})
            mock_verify.return_value = {"sub": "sub-inactive", "email": "inactive@example.com", "email_verified": True}
            with pytest.raises(ValueError, match="deactivated"):
                google_authenticate("code123", "http://localhost:3000")

    def test_raises_when_no_email_field_in_claims(self) -> None:
        with (
            patch("apps.authentication.services.urllib.request.urlopen") as mock_open,
            patch("apps.authentication.services.verify_oauth2_token") as mock_verify,
        ):
            mock_open.return_value = _urlopen_mock({"id_token": "jwt"})
            mock_verify.return_value = {"email_verified": True}
            with pytest.raises(ValueError, match="no email"):
                google_authenticate("code123", "http://localhost:3000")

    def test_matches_existing_user_case_insensitively(self) -> None:
        existing = UserFactory.create(email="mixed@example.com")

        with (
            patch("apps.authentication.services.urllib.request.urlopen") as mock_open,
            patch("apps.authentication.services.verify_oauth2_token") as mock_verify,
        ):
            mock_open.return_value = _urlopen_mock({"id_token": "jwt"})
            mock_verify.return_value = {"sub": "sub-mixed", "email": "Mixed@Example.com", "email_verified": True}
            user = google_authenticate("code123", "http://localhost:3000")

        assert user.pk == existing.pk

    def test_creates_new_user_with_lowercased_email(self) -> None:
        with (
            patch("apps.authentication.services.urllib.request.urlopen") as mock_open,
            patch("apps.authentication.services.verify_oauth2_token") as mock_verify,
        ):
            mock_open.return_value = _urlopen_mock({"id_token": "jwt"})
            mock_verify.return_value = {"sub": "sub-newuser", "email": "New.User@Example.com", "email_verified": True}
            user = google_authenticate("code123", "http://localhost:3000")

        assert user.email == "new.user@example.com"

    def test_reuses_user_created_by_concurrent_login(self) -> None:
        existing = UserFactory.create(email="race@example.com")

        with (
            patch("apps.authentication.services.urllib.request.urlopen") as mock_open,
            patch("apps.authentication.services.verify_oauth2_token") as mock_verify,
            patch("apps.authentication.services.get_user_by_email", side_effect=[None, existing]),
            patch(
                "apps.authentication.services.User.objects.create_user",
                side_effect=IntegrityError("duplicate key value violates unique constraint"),
            ),
        ):
            mock_open.return_value = _urlopen_mock({"id_token": "jwt"})
            mock_verify.return_value = {"sub": "sub-race", "email": "race@example.com", "email_verified": True}
            user = google_authenticate("code123", "http://localhost:3000")

        assert user.pk == existing.pk


@pytest.mark.django_db
class TestUserEmailNormalization:
    def test_save_lowercases_email(self) -> None:
        user = User.objects.create_user(email="Mixed.Case@Example.com")
        assert user.email == "mixed.case@example.com"

    def test_email_unique_is_case_insensitive(self) -> None:
        User.objects.create_user(email="dupe@example.com")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(email="Dupe@Example.com")


@pytest.mark.django_db
class TestIssueTokens:
    def test_returns_two_non_empty_strings(self) -> None:
        user = UserFactory.create()
        access, refresh = issue_tokens(user)
        assert access
        assert refresh

    def test_access_token_contains_role(self) -> None:
        user = UserFactory.create(role=RoleCode.CUSTOMER)
        access, _ = issue_tokens(user)
        assert AccessToken(cast(Token, access)).payload["role"] == RoleCode.CUSTOMER

    def test_access_token_contains_token_version(self) -> None:
        user = UserFactory.create()
        user.__class__.objects.filter(pk=user.pk).update(token_version=5)
        user.refresh_from_db()
        access, _ = issue_tokens(user)
        assert AccessToken(cast(Token, access)).payload["token_version"] == 5


@pytest.mark.django_db
class TestIssueTokensWithRestaurant:
    def test_access_token_contains_restaurant_id(self) -> None:
        from apps.restaurants.models import Restaurant

        restaurant = Restaurant.objects.create(name="Test")
        user = UserFactory.create(role=RoleCode.WAITER)
        access, _ = issue_tokens_with_restaurant(user, restaurant.id)
        payload = AccessToken(cast(Token, access)).payload
        assert payload["restaurant_id"] == restaurant.id
        assert payload["restaurant_public_id"] == str(restaurant.public_id)

    def test_access_token_contains_role_and_token_version(self) -> None:
        from apps.restaurants.models import Restaurant

        restaurant = Restaurant.objects.create(name="Test")
        user = UserFactory.create(role=RoleCode.COOK)
        access, _ = issue_tokens_with_restaurant(user, restaurant.id)
        payload = AccessToken(cast(Token, access)).payload
        assert payload["role"] == RoleCode.COOK
        assert "token_version" in payload
        assert "restaurant_public_id" in payload
