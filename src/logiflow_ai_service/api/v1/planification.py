"""POST /internal/ai/v1/planification/proposer — voir docs/integration-ia.md côté backend."""

from flask import Blueprint, current_app, jsonify, request
from pydantic import ValidationError

from logiflow_ai_service.agents.planification.schemas import PlanificationRequest
from logiflow_ai_service.errors import validation_problem
from logiflow_ai_service.security import require_internal_api_key

bp = Blueprint("planification", __name__, url_prefix="/planification")


@bp.post("/proposer")
@require_internal_api_key
def proposer():
    try:
        payload = PlanificationRequest.model_validate(request.get_json(force=True, silent=False))
    except ValidationError as exc:
        return jsonify(validation_problem(exc)), 400

    reponse = current_app.config["PLANIFICATION_SERVICE"].proposer(payload)
    return jsonify(reponse.model_dump(by_alias=True, mode="json")), 200
