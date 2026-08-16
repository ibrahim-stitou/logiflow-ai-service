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
  `ollama pull llama3.1` puis `ollama serve`
- Accès réseau sortant vers `router.project-osrm.org` (ou une instance OSRM auto-hébergée) pour
  l'agent itinéraire

## Démarrage

```bash
cp .env.example .env
uv sync
make run
```

Le service démarre sur `http://localhost:8000`.

```bash
curl http://localhost:8000/health
```

## Tests

```bash
make test
```

Les tests mockent les appels sortants (Ollama, OSRM) via `respx` — aucune dépendance réseau
réelle n'est nécessaire pour les faire passer.

## Commandes utiles (`Makefile`)

| Commande | Effet |
|---|---|
| `make install` | Installe les dépendances |
| `make run` | Démarre le serveur de développement (rechargement automatique) |
| `make test` | Exécute la suite de tests |
| `make format` | Formate le code (Ruff) |
| `make lint` | Vérifie le style et les erreurs statiques (Ruff) |

## Variables d'environnement

Voir [.env.example](.env.example). `INTERNAL_API_KEY` doit être identique à `AI_SERVICE_API_KEY`
côté `logiflow-backend`.

## Endpoints

Tous préfixés `/internal/ai/v1`, protégés par l'en-tête `X-Internal-Api-Key` :

- `POST /internal/ai/v1/copilot/ask`
- `POST /internal/ai/v1/groupage/analyser`
- `POST /internal/ai/v1/maintenance/recommander` (501 — non implémenté)
- `POST /internal/ai/v1/itinerary/calculer`

`GET /health` est public (sondé par Docker/l'orchestrateur).
