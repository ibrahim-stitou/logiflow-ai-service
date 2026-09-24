"""POST /internal/ai/v1/maintenance/recommander — voir docs/integration-ia.md côté backend."""

from flask import Blueprint, current_app, jsonify, request
from pydantic import ValidationError

from logiflow_ai_service.agents.maintenance.schemas import MaintenanceRequest
from logiflow_ai_service.errors import validation_problem
from logiflow_ai_service.security import require_internal_api_key

bp = Blueprint("maintenance", __name__, url_prefix="/maintenance")


@bp.post("/recommander")
@require_internal_api_key
def recommander():
    try:
        payload = MaintenanceRequest.model_validate(request.get_json(force=True, silent=False))
    except ValidationError as exc:
        return jsonify(validation_problem(exc)), 400

    reponse = current_app.config["MAINTENANCE_SERVICE"].recommander(payload)
    return jsonify(reponse.model_dump(by_alias=True, mode="json")), 200
