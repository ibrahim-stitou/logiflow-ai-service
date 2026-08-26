from flask import Blueprint, request, jsonify
from logiflow_ai_service.services.chauffeur import selectionner_chauffeur
from logiflow_ai_service.audit.logger import log_ia_interaction, log_erreur
import time

chauffeur_bp = Blueprint("chauffeur", __name__, url_prefix="/internal/ai/v1/chauffeur")

@chauffeur_bp.route("/selectionner", methods=["POST"])
def selectionner():
    """Sélectionne le chauffeur le plus adapté pour un voyage."""
    data = request.get_json()
    
    if not data or "chauffeurs" not in data or "voyage" not in data:
        return jsonify({"error": "Champs 'chauffeurs' et 'voyage' manquants"}), 400
    
    user_id = request.headers.get("X-User-Id", "anonymous")
    
    debut = time.time()
    
    try:
        resultat = selectionner_chauffeur(data["chauffeurs"], data["voyage"])
        duree = int((time.time() - debut) * 1000)
        
        log_ia_interaction(
            user_id,
            "chauffeur/selectionner",
            f"Sélection chauffeur pour voyage {data['voyage'].get('id', 'inconnu')}",
            str(resultat),
            True,
            duree
        )
        
        if resultat:
            return jsonify(resultat)
        else:
            return jsonify({"error": "Aucun chauffeur disponible"}), 404
        
    except Exception as e:
        log_erreur("chauffeur/selectionner", str(e), user_id)
        return jsonify({"error": "Erreur interne"}), 500