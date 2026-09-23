# LogiFlow AI Service

Service Flask hébergeant les agents IA du TMS **LogiFlow** : copilote conversationnel, groupage,
maintenance prédictive (à venir) et calcul d'itinéraire. Appelé exclusivement en interne par le
backend Spring Boot (`logiflow-backend`) — jamais exposé au frontend Angular.

Voir [docs/architecture.md](docs/architecture.md) pour le détail de l'architecture et
`docs/integration-ia.md` dans `logiflow-backend` pour le contrat complet entre les deux services.

## Prérequis

- Python 3.13
- [uv](https://docs.astral.sh/uv/) (gestionnaire de dépendances/environnement)
- [Ollama](https://ollama.com/) en local (ou accessible réseau) pour l'agent copilote —
  `ollama pull llama3.1:8b` (chat + tool-calling) et `ollama pull nomic-embed-text`
  (embeddings de la base de connaissance), puis `ollama serve`
- PostgreSQL avec pgvector pour la base **propre** du service (`logiflow_ai`) : fournie par
  `docker compose -f ../logiflow-backend/docker/docker-compose.yml up -d postgres`
  (script `docker/postgres/init/02-ai-database.sql`)
- Accès réseau sortant vers `router.project-osrm.org` (ou une instance OSRM auto-hébergée) pour
  l'agent itinéraire

## Démarrage

```bash
cp .env.example .env
uv sync
make migrate      # schéma copilote de la base logiflow_ai (Alembic)
make ingerer      # optionnel : documentation de logiflow-backend/docs dans la base de connaissance
make run
```

Sur un volume PostgreSQL créé avant l'ajout de la base IA, la créer une fois :

```bash
docker exec -i logiflow-postgres psql -U logiflow -d logiflow < ../logiflow-backend/docker/postgres/init/02-ai-database.sql
```

Le service démarre sur `http://localhost:8000`.

```bash
curl http://localhost:8000/health
```

## Tests

```bash
make test
```

Les tests mockent les appels sortants (Ollama, OSRM, outils Spring) via `respx` et utilisent des
repositories en mémoire — aucune dépendance réseau réelle n'est nécessaire. Les tests des
repositories SQL s'exécutent si `TEST_DATABASE_URL` pointe vers une base PostgreSQL + pgvector
jetable (ils sont ignorés sinon).

## Commandes utiles (`Makefile`)

| Commande | Effet |
|---|---|
| `make install` | Installe les dépendances |
| `make run` | Démarre le serveur de développement (rechargement automatique) |
| `make migrate` | Applique les migrations Alembic sur `DATABASE_URL` |
| `make ingerer SOURCES=…` | Ingère des fichiers .md/.html/.txt dans la base de connaissance |
| `make test` | Exécute la suite de tests |
| `make format` | Formate le code (Ruff) |
| `make lint` | Vérifie le style et les erreurs statiques (Ruff) |

## Variables d'environnement

Voir [.env.example](.env.example). `INTERNAL_API_KEY` doit être identique à `AI_SERVICE_API_KEY`
côté `logiflow-backend`, et `BACKEND_CALLBACK_API_KEY` à `AI_SERVICE_CALLBACK_API_KEY`.

## Endpoints

Tous préfixés `/internal/ai/v1`, protégés par l'en-tête `X-Internal-Api-Key` :

- Copilote (chatbot) : `GET|POST /internal/ai/v1/copilot/conversations`,
  `GET|PATCH|DELETE /internal/ai/v1/copilot/conversations/<id>`,
  `POST /internal/ai/v1/copilot/conversations/<id>/messages` (réponse `text/event-stream`),
  `POST /internal/ai/v1/copilot/messages/<id>/feedback` — utilisateur dans `X-Utilisateur-Id`
- `POST /internal/ai/v1/copilot/ask` (question unique, ancienne version)
- `POST /internal/ai/v1/groupage/analyser`
- `POST /internal/ai/v1/maintenance/recommander` (501 — non implémenté)
- `POST /internal/ai/v1/itinerary/calculer`

`GET /health` est public (sondé par Docker/l'orchestrateur).
