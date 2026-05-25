from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.authentication.models import RoleCode
from apps.authentication.services import issue_tokens
from tests.conftest import UserFactory


@pytest.mark.django_db
class TestGoogleAuthView:
    url = "/api/auth/google/"

    def test_success_returns_access_token_and_sets_cookie(self) -> None:
        user = UserFactory.create()
        with patch("apps.authentication.views.google_authenticate", return_value=user):
            response = APIClient().post(
                self.url,
                {"code": "valid-code", "redirect_uri": "http://localhost:3000"},
                format="json",
            )

        assert response.status_code == 200
        assert "access" in response.data
        assert "refresh_token" in response.cookies
        cookie = response.cookies["refresh_token"]
        assert cookie["httponly"]
        assert cookie["samesite"] == "Strict"

    def test_google_error_returns_400(self) -> None:
        with patch(
            "apps.authentication.views.google_authenticate",
            side_effect=ValueError("invalid_grant"),
        ):
            response = APIClient().post(
                self.url,
                {"code": "bad", "redirect_uri": "http://localhost:3000"},
                format="json",
            )

        assert response.status_code == 400
        assert response.data["detail"] == "invalid_grant"

    def test_missing_code_returns_400(self) -> None:
        response = APIClient().post(self.url, {"redirect_uri": "http://localhost:3000"}, format="json")
        assert response.status_code == 400

    def test_missing_redirect_uri_returns_400(self) -> None:
        response = APIClient().post(self.url, {"code": "abc"}, format="json")
        assert response.status_code == 400


@pytest.mark.django_db
class TestCookieTokenRefreshView:
    url = "/api/auth/refresh/"

    def test_valid_cookie_returns_new_access_token(self) -> None:
        user = UserFactory.create()
        _, refresh = issue_tokens(user)
        client = APIClient()
        client.cookies["refresh_token"] = refresh

        response = client.post(self.url)

        assert response.status_code == 200
        assert "access" in response.data

    def test_no_cookie_returns_401(self) -> None:
        response = APIClient().post(self.url)
        assert response.status_code == 401

    def test_invalid_token_in_cookie_returns_401(self) -> None:
        client = APIClient()
        client.cookies["refresh_token"] = "not.a.valid.token"

        response = client.post(self.url)

        assert response.status_code == 401


@pytest.mark.django_db
class TestLogoutView:
    url = "/api/auth/logout/"

    def test_returns_200_and_clears_cookie(self) -> None:
        user = UserFactory.create()
        _, refresh = issue_tokens(user)
        client = APIClient()
        client.cookies["refresh_token"] = refresh

        response = client.post(self.url)

        assert response.status_code == 200
        assert response.cookies["refresh_token"].value == ""

    def test_logout_without_cookie_still_returns_200(self) -> None:
        response = APIClient().post(self.url)
        assert response.status_code == 200


@pytest.mark.django_db
class TestMeView:
    url = "/api/auth/me/"

    def test_returns_profile_for_authenticated_user(self) -> None:
        user = UserFactory.create(email="me@example.com", role=RoleCode.CUSTOMER)
        access, _ = issue_tokens(user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = client.get(self.url)

        assert response.status_code == 200
        assert response.data["email"] == "me@example.com"
        assert response.data["role"] == RoleCode.CUSTOMER

    def test_unauthenticated_returns_401(self) -> None:
        response = APIClient().get(self.url)
        assert response.status_code == 401

    def test_stale_token_version_returns_401(self) -> None:
        user = UserFactory.create()
        access, _ = issue_tokens(user)
        # Simulate role change that bumped token_version in DB
        user.__class__.objects.filter(pk=user.pk).update(token_version=99)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = client.get(self.url)

        assert response.status_code == 401
