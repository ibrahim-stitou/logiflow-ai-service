"""Point d'entrée de l'application Flask (factory pattern)."""

from urllib.parse import urlparse

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
from logiflow_ai_service.infrastructure.llm_client import LlmClient
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

    llm_client = LlmClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout_s=settings.llm_timeout_s,
        stream_timeout_s=settings.llm_stream_timeout_s,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        embed_base_url=settings.embed_base_url,
        embed_api_key=settings.embed_api_key,
        embed_model=settings.embed_model,
        forcer_tls12=settings.llm_forcer_tls12,
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
        if connaissance_repository is None and llm_client.embeddings_disponibles:
            connaissance_repository = SqlConnaissanceRepository(session_factory)

    orchestrateur = CopiloteOrchestrateur(
        conversation_repository,
        llm_client,
        BoiteOutils(backend_client, llm_client, connaissance_repository),
        max_iterations_outils=settings.copilote_max_iterations_outils,
        historique_max=settings.copilote_historique_max,
        titre_llm=settings.copilote_titre_llm,
        battement_s=settings.copilote_battement_s,
    )

    app.config["LLM_CLIENT"] = llm_client
    app.config["CONNAISSANCE_REPOSITORY"] = connaissance_repository
    app.config["COPILOTE_SERVICE"] = CopiloteService(llm_client)
    app.config["CONVERSATION_SERVICE"] = ConversationService(conversation_repository, orchestrateur)
    app.config["GROUPAGE_SERVICE"] = GroupageService()
    app.config["ITINERARY_SERVICE"] = ItineraryService(osrm_client)

    app.register_blueprint(api_v1_bp)
    register_error_handlers(app)
    enregistrer_commandes(app)

    @app.get("/health")
    def health():
        # Endpoint public (pas de clé API) : sondé par Docker et par Spring (/ia/copilote/etat).
        # Toujours 200 tant que le processus répond (liveness) ; l'état des dépendances (LLM,
        # base) est détaillé pour le diagnostic sans faire échouer la sonde.
        return jsonify(
            {
                "status": "UP",
                "dependances": {
                    # UP, DOWN, CLE_ABSENTE, CLE_INVALIDE ou MODELE_ABSENT.
                    "llm": llm_client.etat(),
                    "base": _etat_base(engine),
                },
                "modele": llm_client.model,
                "fournisseur": urlparse(settings.llm_base_url).hostname,
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
