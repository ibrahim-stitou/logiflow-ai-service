from flask import Blueprint, request, jsonify
from logiflow_ai_service.services.maintenance import calculer_score_sante
from logiflow_ai_service.audit.logger import log_ia_interaction, log_erreur
import time

maintenance_bp = Blueprint("maintenance", __name__, url_prefix="/internal/ai/v1/maintenance")

@maintenance_bp.route("/recommander", methods=["POST"])
def recommander():
    """Recommandation de maintenance pour un véhicule."""
    data = request.get_json()
    
    if not data or "vehiculeId" not in data:
        return jsonify({"error": "Champ 'vehiculeId' manquant"}), 400
    
    user_id = request.headers.get("X-User-Id", "anonymous")
    vehicule_id = data["vehiculeId"]
    
    debut = time.time()
    
    try:
        resultat = calculer_score_sante(vehicule_id)
        duree = int((time.time() - debut) * 1000)
        
        log_ia_interaction(
            user_id,
            "maintenance/recommander",
            f"Véhicule {vehicule_id}",
            str(resultat),
            True,
            duree
        )
        
        return jsonify(resultat)
        
    except Exception as e:
        log_erreur("maintenance/recommander", str(e), user_id)
        return jsonify({"error": "Erreur interne"}), 500