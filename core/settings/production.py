from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False

# SECRET_KEY also signs JWTs (SIMPLE_JWT defaults to it with HS256), so it must
# be a strong, explicitly-set value in production.
if SECRET_KEY == LOCAL_DEV_SECRET_KEY:  # noqa: F405
    raise ImproperlyConfigured("SECRET_KEY must be explicitly set in production and must not use local default.")

if len(SECRET_KEY.encode()) < 32:  # noqa: F405
    raise ImproperlyConfigured(
        "SECRET_KEY must be at least 32 bytes in production (HMAC-SHA256 signing key). "
        "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    )
