.PHONY: install run test format lint

## Installe les dépendances (runtime + dev)
install:
	uv sync

## Démarre le serveur de développement Flask (rechargement automatique)
run:
	uv run flask --app logiflow_ai_service.app:create_app run --port 8000 --debug

## Exécute la suite de tests
test:
	uv run pytest

## Applique le formatage (Ruff)
format:
	uv run ruff format .

## Vérifie le style et les erreurs statiques (Ruff)
lint:
	uv run ruff check .
