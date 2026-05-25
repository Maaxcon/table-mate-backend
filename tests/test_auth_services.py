import json
import urllib.error
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from rest_framework_simplejwt.tokens import AccessToken

from apps.authentication.models import RoleCode
from apps.authentication.services import google_authenticate, issue_tokens
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
        with patch("apps.authentication.services.urllib.request.urlopen") as mock_open:
            mock_open.side_effect = [
                _urlopen_mock({"access_token": "goog-tok"}),
                _urlopen_mock({"email": "new@example.com", "given_name": "John", "family_name": "Doe"}),
            ]
            user = google_authenticate("code123", "http://localhost:3000")

        assert user.email == "new@example.com"
        assert user.first_name == "John"
        assert user.last_name == "Doe"
        assert user.role == RoleCode.CUSTOMER

    def test_returns_existing_user(self) -> None:
        existing = UserFactory.create(email="existing@example.com")

        with patch("apps.authentication.services.urllib.request.urlopen") as mock_open:
            mock_open.side_effect = [
                _urlopen_mock({"access_token": "goog-tok"}),
                _urlopen_mock({"email": "existing@example.com"}),
            ]
            user = google_authenticate("code123", "http://localhost:3000")

        assert user.pk == existing.pk

    def test_raises_on_google_exchange_error(self) -> None:
        with patch(
            "apps.authentication.services.urllib.request.urlopen",
            side_effect=_http_error("invalid_grant"),
        ):
            with pytest.raises(ValueError, match="invalid_grant"):
                google_authenticate("bad-code", "http://localhost:3000")

    def test_raises_when_no_access_token_in_response(self) -> None:
        with patch("apps.authentication.services.urllib.request.urlopen") as mock_open:
            mock_open.return_value = _urlopen_mock({})
            with pytest.raises(ValueError, match="No access token"):
                google_authenticate("code123", "http://localhost:3000")

    def test_raises_when_no_email_in_userinfo(self) -> None:
        with patch("apps.authentication.services.urllib.request.urlopen") as mock_open:
            mock_open.side_effect = [
                _urlopen_mock({"access_token": "goog-tok"}),
                _urlopen_mock({}),
            ]
            with pytest.raises(ValueError, match="no email"):
                google_authenticate("code123", "http://localhost:3000")


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
        assert AccessToken(access).payload["role"] == RoleCode.CUSTOMER

    def test_access_token_contains_token_version(self) -> None:
        user = UserFactory.create()
        user.__class__.objects.filter(pk=user.pk).update(token_version=5)
        user.refresh_from_db()
        access, _ = issue_tokens(user)
        assert AccessToken(access).payload["token_version"] == 5
