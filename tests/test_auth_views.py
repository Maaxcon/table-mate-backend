from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from apps.authentication.models import RoleCode, User
from apps.authentication.services import issue_tokens, issue_tokens_with_restaurant
from apps.reservations.models import Reservation, ReservationStatus
from apps.restaurants.models import Restaurant
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

    def test_customer_gets_refresh_cookie(self) -> None:
        user = UserFactory.create(role=RoleCode.CUSTOMER)
        with patch("apps.authentication.views.google_authenticate", return_value=user):
            response = APIClient().post(
                self.url,
                {"code": "code", "redirect_uri": "http://localhost:3000"},
                format="json",
            )
        assert response.status_code == 200
        assert "refresh_token" in response.cookies
        assert "needs_restaurant_context" not in response.data

    def test_staff_gets_refresh_cookie_and_restaurant_id_in_token(self) -> None:
        restaurant = Restaurant.objects.create(name="Test Restaurant")
        user = UserFactory.create(role=RoleCode.WAITER, restaurant=restaurant)
        with patch("apps.authentication.views.google_authenticate", return_value=user):
            response = APIClient().post(
                self.url,
                {"code": "code", "redirect_uri": "http://localhost:3000"},
                format="json",
            )
        assert response.status_code == 200
        assert "access" in response.data
        assert "refresh_token" in response.cookies
        from rest_framework_simplejwt.tokens import AccessToken

        token = AccessToken(response.data["access"])
        assert token.payload.get("restaurant_id") == restaurant.pk


@pytest.mark.django_db
class TestGoogleContextView:
    url = "/api/auth/google/context/"

    def test_valid_restaurant_issues_full_tokens(self) -> None:
        restaurant = Restaurant.objects.create(name="Test Restaurant")
        user = UserFactory.create(role=RoleCode.WAITER, restaurant=restaurant)
        access, _ = issue_tokens(user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = client.post(self.url, {"restaurant_id": restaurant.pk}, format="json")

        assert response.status_code == 200
        assert "access" in response.data
        assert "refresh_token" in response.cookies

    def test_wrong_restaurant_returns_403(self) -> None:
        restaurant = Restaurant.objects.create(name="Restaurant A")
        other = Restaurant.objects.create(name="Restaurant B")
        user = UserFactory.create(role=RoleCode.WAITER, restaurant=restaurant)
        access, _ = issue_tokens(user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = client.post(self.url, {"restaurant_id": other.pk}, format="json")

        assert response.status_code == 403
        assert "detail" in response.data

    def test_unauthenticated_returns_401(self) -> None:
        response = APIClient().post(self.url, {"restaurant_id": 1}, format="json")
        assert response.status_code == 401

    def test_customer_cannot_use_context_endpoint(self) -> None:
        user = UserFactory.create(role=RoleCode.CUSTOMER)
        access, _ = issue_tokens(user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = client.post(self.url, {"restaurant_id": 1}, format="json")

        assert response.status_code == 403

    def test_missing_restaurant_id_returns_400(self) -> None:
        user = UserFactory.create(role=RoleCode.WAITER)
        access, _ = issue_tokens(user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = client.post(self.url, {}, format="json")

        assert response.status_code == 400


@pytest.mark.django_db
class TestTokenClaims:
    def test_full_token_contains_restaurant_id(self) -> None:
        from rest_framework_simplejwt.tokens import AccessToken, Token

        restaurant = Restaurant.objects.create(name="Test Restaurant")
        user = UserFactory.create(role=RoleCode.WAITER, restaurant=restaurant)
        access, _ = issue_tokens_with_restaurant(user, restaurant.pk)

        token = AccessToken(token=cast(Token, access))
        assert token.payload["restaurant_id"] == restaurant.pk


@pytest.mark.django_db
class TestCustomerContextView:
    url = "/api/auth/customer/context/"

    def _create_reservation(self, *, restaurant: Restaurant, customer: User) -> Reservation:
        start = datetime.now(UTC) + timedelta(hours=1)
        return Reservation.objects.create(
            restaurant=restaurant,
            customer=customer,
            guest_count=2,
            start_at=start,
            end_at=start + timedelta(hours=2),
            status=ReservationStatus.ACTIVE,
        )

    def test_customer_participant_gets_restaurant_token(self) -> None:
        restaurant = Restaurant.objects.create(name="Test Restaurant")
        user = UserFactory.create(role=RoleCode.CUSTOMER)
        reservation = self._create_reservation(restaurant=restaurant, customer=user)
        access, _ = issue_tokens(user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = client.post(self.url, {"reservation": str(reservation.public_id)}, format="json")

        assert response.status_code == 200
        assert "access" in response.data
        assert "refresh_token" in response.cookies

    def test_reservation_participant_gets_token(self) -> None:
        restaurant = Restaurant.objects.create(name="Test Restaurant")
        owner = UserFactory.create(role=RoleCode.CUSTOMER)
        participant = UserFactory.create(role=RoleCode.CUSTOMER)
        reservation = self._create_reservation(restaurant=restaurant, customer=owner)
        reservation.participants.add(participant)
        access, _ = issue_tokens(participant)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = client.post(self.url, {"reservation": str(reservation.public_id)}, format="json")

        assert response.status_code == 200

    def test_non_participant_returns_403(self) -> None:
        restaurant = Restaurant.objects.create(name="Test Restaurant")
        owner = UserFactory.create(role=RoleCode.CUSTOMER)
        stranger = UserFactory.create(role=RoleCode.CUSTOMER)
        reservation = self._create_reservation(restaurant=restaurant, customer=owner)
        access, _ = issue_tokens(stranger)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = client.post(self.url, {"reservation": str(reservation.public_id)}, format="json")

        assert response.status_code == 403

    def test_staff_cannot_use_customer_endpoint(self) -> None:
        restaurant = Restaurant.objects.create(name="Test Restaurant")
        staff = UserFactory.create(role=RoleCode.WAITER, restaurant=restaurant)
        reservation = self._create_reservation(restaurant=restaurant, customer=UserFactory.create())
        access, _ = issue_tokens(staff)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = client.post(self.url, {"reservation": str(reservation.public_id)}, format="json")

        assert response.status_code == 403

    def test_unauthenticated_returns_401(self) -> None:
        response = APIClient().post(self.url, {"reservation": str(uuid4())}, format="json")

        assert response.status_code == 401


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

    def test_rotated_refresh_written_to_cookie_not_body(self) -> None:
        user = UserFactory.create()
        _, refresh = issue_tokens(user)
        client = APIClient()
        client.cookies["refresh_token"] = refresh

        new_refresh = "new.refresh.token"
        with patch("apps.authentication.views.CookieTokenRefreshView.get_serializer") as mock_ser:
            mock_instance = mock_ser.return_value
            mock_instance.is_valid.return_value = None
            mock_instance.validated_data = {"access": "new.access.token", "refresh": new_refresh}

            response = client.post(self.url)

        assert response.status_code == 200
        assert "refresh" not in response.data
        assert response.cookies["refresh_token"].value == new_refresh

    def test_no_cookie_returns_401(self) -> None:
        response = APIClient().post(self.url)
        assert response.status_code == 401

    def test_invalid_token_in_cookie_returns_401(self) -> None:
        client = APIClient()
        client.cookies["refresh_token"] = "not.a.valid.token"

        response = client.post(self.url)

        assert response.status_code == 401

    def test_stale_token_version_after_role_change_returns_401(self) -> None:
        # A role change bumps token_version, so a refresh token issued before it
        # must be rejected (forces a fresh login instead of looping on 401s).
        user = UserFactory.create()
        _, refresh = issue_tokens(user)
        user.token_version += 1
        user.save(update_fields=["token_version"])
        client = APIClient()
        client.cookies["refresh_token"] = refresh

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

    def test_token_without_version_claim_returns_401(self) -> None:
        from rest_framework_simplejwt.tokens import AccessToken

        user = UserFactory.create()
        # AccessToken.for_user does not embed token_version (only issue_tokens does)
        token = AccessToken.for_user(user)
        assert "token_version" not in token.payload
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(token)}")

        response = client.get(self.url)

        assert response.status_code == 401


@pytest.mark.django_db
class TestMeUpdate:
    url = "/api/auth/me/"

    def _client(self, user: User) -> APIClient:
        access, _ = issue_tokens(user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        return client

    def test_updates_name_and_phone(self) -> None:
        user = UserFactory.create(role=RoleCode.CUSTOMER, first_name="Old", last_name="Name")
        client = self._client(user)

        response = client.patch(
            self.url,
            {"first_name": "New", "last_name": "Person", "phone": "+10000000000"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["first_name"] == "New"
        assert response.data["last_name"] == "Person"
        assert response.data["phone"] == "+10000000000"
        user.refresh_from_db()
        assert user.first_name == "New"
        assert user.phone == "+10000000000"

    def test_email_is_read_only(self) -> None:
        user = UserFactory.create(role=RoleCode.CUSTOMER, email="before@example.com")
        client = self._client(user)

        response = client.patch(self.url, {"email": "after@example.com"}, format="json")

        assert response.status_code == 200
        user.refresh_from_db()
        # Email is the Google identity — it must not change here.
        assert user.email == "before@example.com"

    def test_cannot_change_role(self) -> None:
        user = UserFactory.create(role=RoleCode.CUSTOMER)
        client = self._client(user)

        response = client.patch(self.url, {"role": RoleCode.ADMIN}, format="json")

        assert response.status_code == 200
        user.refresh_from_db()
        # role is not editable — it stays customer.
        assert user.role == RoleCode.CUSTOMER

    def test_unauthenticated_returns_401(self) -> None:
        response = APIClient().patch(self.url, {"first_name": "X"}, format="json")
        assert response.status_code == 401


@pytest.mark.django_db
class TestAuthThrottling:
    url = "/api/auth/google/"

    def test_login_endpoint_is_rate_limited(self) -> None:
        # "auth" scope is 10/min; the 11th request from the same IP is blocked.
        client = APIClient()
        payload = {"code": "x", "redirect_uri": "http://localhost:3000"}
        statuses = [client.post(self.url, payload, format="json").status_code for _ in range(11)]

        assert 429 not in statuses[:10]
        assert statuses[-1] == 429
