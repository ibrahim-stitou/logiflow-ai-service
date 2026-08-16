"""Regroupe les blueprints des agents sous /internal/ai/v1 (jamais appelé par Angular)."""

from flask import Blueprint

from logiflow_ai_service.api.v1.copilot import bp as copilot_bp
from logiflow_ai_service.api.v1.groupage import bp as groupage_bp
from logiflow_ai_service.api.v1.itinerary import bp as itinerary_bp
from logiflow_ai_service.api.v1.maintenance import bp as maintenance_bp

bp = Blueprint("v1", __name__, url_prefix="/internal/ai/v1")
bp.register_blueprint(copilot_bp)
bp.register_blueprint(groupage_bp)
bp.register_blueprint(maintenance_bp)
bp.register_blueprint(itinerary_bp)
