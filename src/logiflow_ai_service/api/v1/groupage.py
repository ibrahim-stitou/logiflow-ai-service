"""POST /internal/ai/v1/groupage/analyser — voir docs/integration-ia.md côté backend."""

import logging

from flask import Blueprint, current_app, jsonify, request
from pydantic import ValidationError

from logiflow_ai_service.agents.groupage.schemas import GroupageAnalyserRequest
from logiflow_ai_service.errors import validation_problem
from logiflow_ai_service.security import require_internal_api_key

logger = logging.getLogger(__name__)

bp = Blueprint("groupage", __name__, url_prefix="/groupage")


@bp.post("/analyser")
@require_internal_api_key
def analyser():
    try:
        payload = GroupageAnalyserRequest.model_validate(request.get_json(force=True, silent=False))
    except ValidationError as exc:
        return jsonify(validation_problem(exc)), 400

    reponse = current_app.config["GROUPAGE_SERVICE"].analyser(payload)
    return jsonify(reponse.model_dump(by_alias=True)), 200
