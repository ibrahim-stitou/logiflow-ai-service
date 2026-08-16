"""POST /internal/ai/v1/copilot/ask — voir docs/integration-ia.md côté backend."""

import logging

from flask import Blueprint, current_app, jsonify, request
from pydantic import ValidationError

from logiflow_ai_service.agents.copilot.schemas import CopilotAskRequest
from logiflow_ai_service.errors import validation_problem
from logiflow_ai_service.infrastructure.exceptions import UpstreamServiceError
from logiflow_ai_service.security import require_internal_api_key

logger = logging.getLogger(__name__)

bp = Blueprint("copilot", __name__, url_prefix="/copilot")


@bp.post("/ask")
@require_internal_api_key
def ask():
    try:
        payload = CopilotAskRequest.model_validate(request.get_json(force=True, silent=False))
    except ValidationError as exc:
        return jsonify(validation_problem(exc)), 400

    try:
        reponse = current_app.config["COPILOTE_SERVICE"].repondre(payload)
    except UpstreamServiceError:
        logger.warning("Agent copilote indisponible (Ollama injoignable)", exc_info=True)
        return jsonify({"title": "Service IA indisponible", "status": 503}), 503

    return jsonify(reponse.model_dump(by_alias=True)), 200
