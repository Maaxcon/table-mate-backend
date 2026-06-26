"""Exercises the real id_token verifier (not a mock) so a regression that drops
the audience/signature/issuer/expiry checks fails CI. Only the certificate
transport is stubbed; google's verification logic runs for real."""

import time
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import jwt as google_jwt
from google.auth.crypt import RSASigner

from apps.authentication.services import verify_google_id_token

TEST_AUDIENCE = "test-client-id.apps.googleusercontent.com"
TEST_KID = "test-kid"


def _generate_keypair() -> tuple[bytes, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem.decode()


def _sign(private_pem: bytes, kid: str, **claim_overrides: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": "https://accounts.google.com",
        "aud": TEST_AUDIENCE,
        "sub": "google-sub-123",
        "email": "user@example.com",
        "email_verified": True,
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(claim_overrides)
    signer = RSASigner.from_string(private_pem, key_id=kid)  # type: ignore[no-untyped-call]
    token: bytes = google_jwt.encode(signer, claims)  # type: ignore[no-untyped-call]
    return token.decode()


@pytest.fixture
def signing_key() -> Iterator[bytes]:
    """Yields a private key whose matching public cert is served to the verifier."""
    private_pem, public_pem = _generate_keypair()
    with patch("google.oauth2.id_token._fetch_certs", return_value={TEST_KID: public_pem}):
        yield private_pem


class TestVerifyGoogleIdToken:
    @pytest.fixture(autouse=True)
    def _set_client_id(self, settings: Any) -> None:
        settings.GOOGLE_CLIENT_ID = TEST_AUDIENCE

    def test_accepts_valid_token(self, signing_key: bytes) -> None:
        claims = verify_google_id_token(_sign(signing_key, TEST_KID))
        assert claims["email"] == "user@example.com"
        assert claims["aud"] == TEST_AUDIENCE

    def test_rejects_wrong_audience(self, signing_key: bytes) -> None:
        token = _sign(signing_key, TEST_KID, aud="attacker-app.apps.googleusercontent.com")
        with pytest.raises(ValueError):
            verify_google_id_token(token)

    def test_rejects_expired_token(self, signing_key: bytes) -> None:
        now = int(time.time())
        token = _sign(signing_key, TEST_KID, iat=now - 7200, exp=now - 3600)
        with pytest.raises(ValueError):
            verify_google_id_token(token)

    def test_rejects_wrong_issuer(self, signing_key: bytes) -> None:
        # google raises GoogleAuthError (not ValueError) here; the wrapper must
        # still surface a ValueError so the view returns 400, not 500.
        token = _sign(signing_key, TEST_KID, iss="https://evil.example.com")
        with pytest.raises(ValueError):
            verify_google_id_token(token)

    def test_rejects_bad_signature(self) -> None:
        attacker_key, _ = _generate_keypair()
        _, honest_public = _generate_keypair()
        token = _sign(attacker_key, TEST_KID)
        with patch("google.oauth2.id_token._fetch_certs", return_value={TEST_KID: honest_public}):
            with pytest.raises(ValueError):
                verify_google_id_token(token)
