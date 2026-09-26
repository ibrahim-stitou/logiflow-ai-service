FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# uv épinglé : build reproductible (pas de « latest »).
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /uvx /bin/

# Couche dépendances mise en cache indépendamment du code source applicatif.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN uv sync --frozen --no-dev

# Exécution sans privilèges : utilisateur dédié, sans droit d'écriture sur le code.
RUN groupadd --system --gid 10001 logiflow \
    && useradd --system --uid 10001 --gid logiflow --home-dir /app --no-create-home logiflow
USER logiflow

EXPOSE 8000

# Workers gthread : une réponse du copilote est streamée (SSE) pendant plusieurs dizaines de
# secondes ; des workers sync seraient bloqués un par flux. --timeout couvre un flux complet.
# Les migrations Alembic sont appliquées au démarrage (idempotent). L'environnement virtuel est
# utilisé directement (pas de « uv run », qui pourrait tenter de le resynchroniser).
CMD ["sh", "-c", "alembic upgrade head && exec gunicorn --bind 0.0.0.0:8000 --workers 2 --worker-class gthread --threads 8 --timeout 180 logiflow_ai_service.wsgi:app"]
