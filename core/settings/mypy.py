import os

# Mypy imports Django settings through django-stubs plugin.
# These defaults are test-only and prevent env-related crashes in CI/hooks.
os.environ.setdefault("SECRET_KEY", "mypy-secret-key")
os.environ.setdefault("ALLOWED_HOSTS", "localhost,127.0.0.1")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from .local import *  # noqa: F403
