.PHONY: install run test format lint migrate ingerer

## Installe les dépendances (runtime + dev)
install:
	uv sync

## Démarre le serveur de développement Flask (rechargement automatique)
run:
	uv run flask --app logiflow_ai_service.app:create_app run --port 8000 --debug

## Applique les migrations de la base propre au service IA (DATABASE_URL)
migrate:
	uv run alembic upgrade head

## Ingère la documentation fonctionnelle dans la base de connaissance du copilote
## Usage : make ingerer SOURCES="../logiflow-backend/docs"
SOURCES ?= ../logiflow-backend/docs
ingerer:
	uv run flask --app logiflow_ai_service.app:create_app ingerer $(SOURCES)

## Exécute la suite de tests (TEST_DATABASE_URL=... active les tests SQL)
test:
	uv run pytest

## Applique le formatage (Ruff)
format:
	uv run ruff format .

## Vérifie le style et les erreurs statiques (Ruff)
lint:
	uv run ruff check .
