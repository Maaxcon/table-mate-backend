from .base import *  # noqa: F401,F403

DEBUG = True

REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # type: ignore[name-defined]  # noqa: F405
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.authentication.authentication.TokenVersionJWTAuthentication",
    ],
}

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
