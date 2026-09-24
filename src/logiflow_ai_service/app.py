"""Point d'entrée de l'application Flask (factory pattern)."""

from flask import Flask, jsonify
from sqlalchemy import text

from logiflow_ai_service.agents.copilot.model import (
    ConnaissanceRepository,
    ConversationRepository,
)
from logiflow_ai_service.agents.copilot.orchestrateur import CopiloteOrchestrateur
from logiflow_ai_service.agents.copilot.outils import BoiteOutils
from logiflow_ai_service.agents.copilot.service import ConversationService, CopiloteService
from logiflow_ai_service.agents.groupage.service import GroupageService
from logiflow_ai_service.agents.itinerary.service import ItineraryService
from logiflow_ai_service.api.v1 import bp as api_v1_bp
from logiflow_ai_service.cli import enregistrer_commandes
from logiflow_ai_service.config import Settings, get_settings
from logiflow_ai_service.errors import register_error_handlers
from logiflow_ai_service.infrastructure.backend_client import BackendClient
from logiflow_ai_service.infrastructure.db import creer_engine, creer_session_factory
from logiflow_ai_service.infrastructure.ollama_client import OllamaClient
from logiflow_ai_service.infrastructure.osrm_client import OsrmClient
from logiflow_ai_service.infrastructure.persistence.connaissance_repository import (
    SqlConnaissanceRepository,
)
from logiflow_ai_service.infrastructure.persistence.conversation_repository import (
    SqlConversationRepository,
)
from logiflow_ai_service.logging_config import configure_logging


def create_app(
    settings: Settings | None = None,
    *,
    conversation_repository: ConversationRepository | None = None,
    connaissance_repository: ConnaissanceRepository | None = None,
) -> Flask:
    """Les repositories sont injectables (tests en mémoire) ; par défaut, PostgreSQL."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = Flask(__name__)
    app.config["SETTINGS"] = settings

    ollama_client = OllamaClient(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_s=settings.ollama_timeout_s,
        stream_timeout_s=settings.ollama_stream_timeout_s,
        embed_model=settings.ollama_embed_model,
        num_ctx=settings.ollama_num_ctx,
        temperature=settings.ollama_temperature,
    )
    osrm_client = OsrmClient(base_url=settings.osrm_base_url, timeout_s=settings.osrm_timeout_s)
    backend_client = BackendClient(
        base_url=settings.backend_base_url,
        api_key=settings.backend_callback_api_key,
        timeout_s=settings.backend_timeout_s,
    )

    engine = None
    if conversation_repository is None:
        engine = creer_engine(settings.database_url)
        session_factory = creer_session_factory(engine)
        conversation_repository = SqlConversationRepository(session_factory)
        connaissance_repository = connaissance_repository or SqlConnaissanceRepository(
            session_factory
        )

    orchestrateur = CopiloteOrchestrateur(
        conversation_repository,
        ollama_client,
        BoiteOutils(backend_client, ollama_client, connaissance_repository),
        max_iterations_outils=settings.copilote_max_iterations_outils,
        historique_max=settings.copilote_historique_max,
        titre_llm=settings.copilote_titre_llm,
        battement_s=settings.copilote_battement_s,
    )

    app.config["OLLAMA_CLIENT"] = ollama_client
    app.config["CONNAISSANCE_REPOSITORY"] = connaissance_repository
    app.config["COPILOTE_SERVICE"] = CopiloteService(ollama_client)
    app.config["CONVERSATION_SERVICE"] = ConversationService(conversation_repository, orchestrateur)
    app.config["GROUPAGE_SERVICE"] = GroupageService()
    app.config["ITINERARY_SERVICE"] = ItineraryService(osrm_client)

    app.register_blueprint(api_v1_bp)
    register_error_handlers(app)
    enregistrer_commandes(app)

    @app.get("/health")
    def health():
        # Endpoint public (pas de clé API) : sondé par Docker/l'orchestrateur, pas par Spring
        # Boot. Toujours 200 tant que le processus répond (liveness) ; l'état des dépendances
        # (Ollama, base) est détaillé pour le diagnostic sans faire échouer la sonde.
        return jsonify(
            {
                "status": "UP",
                "dependances": {
                    # UP, DOWN, ou MODELE_ABSENT (serveur joignable mais `ollama pull` à faire).
                    "ollama": ollama_client.etat(),
                    "base": _etat_base(engine),
                },
                "modele": ollama_client.model,
            }
        ), 200

    return app


def _etat_base(engine) -> str:
    if engine is None:
        return "N/A"
    try:
        with engine.connect() as connexion:
            connexion.execute(text("SELECT 1"))
        return "UP"
    except Exception:
        return "DOWN"
