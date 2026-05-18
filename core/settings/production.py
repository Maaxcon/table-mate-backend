from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False

if SECRET_KEY == LOCAL_DEV_SECRET_KEY:  # noqa: F405
    raise ImproperlyConfigured(
        'SECRET_KEY must be explicitly set in production and must not use local default.'
    )
