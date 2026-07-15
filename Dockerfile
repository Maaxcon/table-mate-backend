FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/opt/venv

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --group prod --no-install-project

COPY . .

RUN uv sync --frozen --no-dev --group prod

RUN apt-get update && apt-get install -y --no-install-recommends supervisor && rm -rf /var/lib/apt/lists/*

COPY supervisord.conf /app/supervisord.conf

RUN chmod +x entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]

ENV PATH="/opt/venv/bin:$PATH"
ENV DJANGO_SETTINGS_MODULE="core.settings.production"

EXPOSE 8000

CMD ["supervisord", "-c", "/app/supervisord.conf"]

FROM base AS test

RUN uv sync --frozen --group dev --group prod

ENV DJANGO_SETTINGS_MODULE="core.settings.local"
