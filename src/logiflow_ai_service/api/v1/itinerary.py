"""POST /internal/ai/v1/itinerary/calculer — voir docs/integration-ia.md côté backend."""

import logging

from flask import Blueprint, current_app, jsonify, request
from pydantic import ValidationError

from logiflow_ai_service.agents.itinerary.schemas import ItineraryCalculerRequest
from logiflow_ai_service.errors import validation_problem
from logiflow_ai_service.infrastructure.exceptions import UpstreamServiceError
from logiflow_ai_service.security import require_internal_api_key

logger = logging.getLogger(__name__)

bp = Blueprint("itinerary", __name__, url_prefix="/itinerary")


@bp.post("/calculer")
@require_internal_api_key
def calculer():
    try:
        payload = ItineraryCalculerRequest.model_validate(
            request.get_json(force=True, silent=False)
        )
    except ValidationError as exc:
        return jsonify(validation_problem(exc)), 400

    try:
        reponse = current_app.config["ITINERARY_SERVICE"].calculer(payload)
    except UpstreamServiceError:
        logger.warning("Agent itinéraire indisponible (OSRM injoignable)", exc_info=True)
        return jsonify({"title": "Service IA indisponible", "status": 503}), 503

    return jsonify(reponse.model_dump(by_alias=True)), 200
