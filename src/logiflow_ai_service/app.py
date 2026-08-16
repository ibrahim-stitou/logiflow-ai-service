"""Point d'entrée de l'application Flask (factory pattern)."""

from flask import Flask, jsonify

from logiflow_ai_service.agents.copilot.service import CopiloteService
from logiflow_ai_service.agents.groupage.service import GroupageService
from logiflow_ai_service.agents.itinerary.service import ItineraryService
from logiflow_ai_service.api.v1 import bp as api_v1_bp
from logiflow_ai_service.config import Settings, get_settings
from logiflow_ai_service.errors import register_error_handlers
from logiflow_ai_service.infrastructure.ollama_client import OllamaClient
from logiflow_ai_service.infrastructure.osrm_client import OsrmClient
from logiflow_ai_service.logging_config import configure_logging


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = Flask(__name__)
    app.config["SETTINGS"] = settings

    ollama_client = OllamaClient(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_s=settings.ollama_timeout_s,
    )
    osrm_client = OsrmClient(base_url=settings.osrm_base_url, timeout_s=settings.osrm_timeout_s)

    app.config["COPILOTE_SERVICE"] = CopiloteService(ollama_client)
    app.config["GROUPAGE_SERVICE"] = GroupageService()
    app.config["ITINERARY_SERVICE"] = ItineraryService(osrm_client)

    app.register_blueprint(api_v1_bp)
    register_error_handlers(app)

    @app.get("/health")
    def health():
        # Endpoint public (pas de clé API) : sondé par Docker/l'orchestrateur, pas par Spring
        # Boot. Ne vérifie pas la disponibilité d'Ollama/OSRM (readiness applicative, pas
        # dépendance à un service tiers qui peut légitimement fluctuer).
        return jsonify({"status": "UP"}), 200

    return app
