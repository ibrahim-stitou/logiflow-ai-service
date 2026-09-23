FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Couche dépendances mise en cache indépendamment du code source applicatif.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN uv sync --frozen --no-dev

EXPOSE 8000

# Workers gthread : une réponse du copilote est streamée (SSE) pendant plusieurs dizaines de
# secondes ; des workers sync seraient bloqués un par flux. --timeout couvre un flux complet.
# Les migrations Alembic sont appliquées au démarrage (idempotent).
CMD ["sh", "-c", "uv run alembic upgrade head && uv run gunicorn --bind 0.0.0.0:8000 --workers 2 --worker-class gthread --threads 8 --timeout 180 logiflow_ai_service.wsgi:app"]
