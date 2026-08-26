from flask import Blueprint, request, jsonify
from logiflow_ai_service.services.maintenance import calculer_score_sante
from logiflow_ai_service.audit.logger import log_ia_interaction, log_erreur
import time

maintenance_bp = Blueprint("maintenance", __name__, url_prefix="/internal/ai/v1/maintenance")

@maintenance_bp.route("/recommander", methods=["POST"])
def recommander():
    """Recommandation de maintenance pour un véhicule."""
    data = request.get_json()
    
    # Debug
    print(f"🔍 Données reçues: {data}")
    
    # Vérification des données
    if not data:
        print("❌ data est None ou vide")
        return jsonify({"error": "Données manquantes"}), 400
    
    if "vehicule" not in data:
        print(f"❌ La clé 'vehicule' n'existe pas. Clés disponibles: {data.keys()}")
        return jsonify({"error": "Champ 'vehicule' manquant"}), 400
    
    user_id = request.headers.get("X-User-Id", "anonymous")
    vehicule = data["vehicule"]
    
    print(f"✅ Données valides, véhicule: {vehicule}")
    
    debut = time.time()
    
    try:
        resultat = calculer_score_sante(vehicule)
        duree = int((time.time() - debut) * 1000)
        
        log_ia_interaction(
            user_id,
            "maintenance/recommander",
            f"Véhicule {vehicule.get('id', 'inconnu')}",
            str(resultat),
            True,
            duree
        )
        
        return jsonify(resultat)
        
    except Exception as e:
        log_erreur("maintenance/recommander", str(e), user_id)
        print(f"❌ Erreur: {e}")
        return jsonify({"error": "Erreur interne"}), 500