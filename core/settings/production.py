from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False

# Behind the TLS-terminating reverse proxy (Cloudflare/nginx), Django is reached
# over plain HTTP, so without this request.scheme would be "http". DRF then builds
# ImageField URLs (menu item images, restaurant covers) and receipts links via
# request.build_absolute_uri() as http://…, which browsers block as mixed content
# on the HTTPS page. Trusting the proxy's X-Forwarded-Proto header makes
# request.is_secure()/build_absolute_uri() report HTTPS. Safe only because the
# proxy always overwrites this header; the origin must not be reachable directly.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = [
    "https://tablemate.unibrix.net",
]
# SECRET_KEY also signs JWTs (SIMPLE_JWT defaults to it with HS256), so it must
# be a strong, explicitly-set value in production.
if SECRET_KEY == LOCAL_DEV_SECRET_KEY:  # noqa: F405
    raise ImproperlyConfigured("SECRET_KEY must be explicitly set in production and must not use local default.")

if len(SECRET_KEY.encode()) < 32:  # noqa: F405
    raise ImproperlyConfigured(
        "SECRET_KEY must be at least 32 bytes in production (HMAC-SHA256 signing key). "
        'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
    )
