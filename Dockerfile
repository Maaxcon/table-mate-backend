FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/opt/venv

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --group prod --no-install-project

COPY . .

RUN uv sync --frozen --no-dev --group prod

ENV PATH="/opt/venv/bin:$PATH"
ENV DJANGO_SETTINGS_MODULE="core.settings.production"

EXPOSE 8000

CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8000"]

FROM base AS test

RUN uv sync --frozen --group dev --group prod

ENV DJANGO_SETTINGS_MODULE="core.settings.local"
